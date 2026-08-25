"""
Phase 4 evaluator validation tests (deterministic — NO LLM required).

Covers the required scenarios:
1. correct answer -> PASS            5. semantic sequence ok, exact seq differs
2. incorrect numeric answer -> FAIL  6. infrastructure error classification
3. partially correct answer -> PARTIAL 7. tool output correctly used
4. unsupported RAG claim detected     8. tool output ignored
"""

import pytest

from evaluation.metrics.quality import (
    normalize_case,
    evaluate_acceptable_sequences,
    evaluate_task_completion,
    evaluate_tool_grounded,
    evaluate_utilization,
    classify_failure_v2,
    composite_score,
    extract_numbers,
    numbers_equal,
)
from evaluation.metrics.judge import split_claims, deterministic_faithfulness


def _case(**kw):
    base = {"id": "t", "query": "q"}
    base.update(kw)
    return normalize_case(base)


# 1. Correct answer -> PASS
def test_correct_numeric_answer_passes():
    g = evaluate_tool_grounded(
        "The result is 625,000.",
        [{"tool": "calculator", "arguments": {"expression": "125000000 * 0.005"},
          "result": "625000.0"}],
        context="", tools_required=True)
    assert g["applicable"] and g["pass"] is True and g["score"] == 1.0


# 2. Incorrect numeric answer -> FAIL
def test_wrong_magnitude_fails_groundedness():
    g = evaluate_tool_grounded(
        "The result is 6,250,000.",
        [{"tool": "calculator", "arguments": {}, "result": "625000"}],
        context="", tools_required=True)
    assert g["pass"] is False
    assert 6250000 in g["ungrounded"]


# 3. Partially correct answer -> PARTIAL (score between)
def test_partial_grounding_scores_between():
    g = evaluate_tool_grounded(
        "Stipend is $1000; total for 3 employees is 9999.",
        [{"tool": "calculator", "arguments": {}, "result": "3000"},
         {"tool": "web_search", "arguments": {}, "result": "$1,000 stipend"}],
        context="stipend of $1,000", tools_required=True)
    assert 0.0 < g["score"] < 1.0


# 4. Unsupported RAG claim detected (deterministic claim layer)
def test_unsupported_claim_flagged():
    ctx = "Employees receive 20 PTO days per year."
    ans = "Employees receive 20 PTO days. They may also carry over every unused day indefinitely."
    res = deterministic_faithfulness(ctx, ans)
    assert res["claims_total"] >= 2
    assert any("carry over" in u for u in res["unsupported"])
    assert res["score"] < 1.0


# 5. Same operations, different sequence: task completion PASS, exact sequence FAIL
def test_consolidated_search_completion_vs_sequence():
    case = _case(
        expected_sequence=["web_search", "web_search", "calculator"],
        acceptable_tool_sequences=[["web_search", "calculator"]],
        operations=[
            {"op_id": "pops", "tool": "web_search", "must_cover": ["brazil", "argentina"]},
            {"op_id": "diff", "tool": "calculator", "depends_on_output": True},
        ],
    )
    tool_results = [
        {"tool": "web_search", "arguments": {"query": "Brazil Argentina population"},
         "result": "Brazil 212 million ... Argentina 46 million"},
        {"tool": "calculator", "arguments": {"expression": "212000000 - 46000000"},
         "result": "166000000"},
    ]
    tc = evaluate_task_completion(case, ["web_search", "calculator"], tool_results,
                                  rag_context="", final_answer="166 million difference")
    assert tc["complete"] is True                      # task done
    seq = evaluate_acceptable_sequences(case["acceptable_tool_sequences"],
                                        ["web_search", "calculator"])
    assert seq["match"] is True                        # declared-acceptable
    exact = (case["expected_sequence"] == ["web_search", "calculator"])
    assert exact is False                              # but not the canonical path


# 6. Infrastructure failure classified separately
def test_dns_error_is_infrastructure_failure():
    primary, secondary = classify_failure_v2(
        state_error="ConnectError('... dns error: no records found')")
    assert primary == "INFRASTRUCTURE_FAILURE"
    assert secondary == []


# 7. Tool output correctly used (chaining + final citation)
def test_utilization_full_chain():
    case = _case(expected_sequence=["web_search", "calculator"],
                 operations=[
                     {"op_id": "lookup", "tool": "web_search",
                      "must_cover": ["population of japan"]},
                     {"op_id": "calc", "tool": "calculator"}])
    tr = [{"tool": "web_search", "arguments": {"query": "population of Japan"},
           "result": "Japan population is 122,704,252"},
          {"tool": "calculator",
           "arguments": {"expression": "122704252 * 0.005"}, "result": "613521.26"}]
    u = evaluate_utilization(case, tr, "", "Population 122,704,252; 0.5% = 613,521.", None)
    assert u["rate"] == 1.0


# 8. Tool output ignored
def test_utilization_zero_when_ignored():
    case = _case(expected_sequence=["web_search", "calculator"],
                 operations=[
                     {"op_id": "lookup", "tool": "web_search",
                      "must_cover": ["population of japan"]},
                     {"op_id": "calc", "tool": "calculator"}])
    tr = [{"tool": "web_search", "arguments": {}, "result": "Japan population 122704252"},
          {"tool": "calculator", "arguments": {"expression": "2+2"}, "result": "4"}]
    u = evaluate_utilization(case, tr, "", "I could not determine it.", None)
    assert u["rate"] == 0.0
    assert set(u["unused"]) == {"lookup", "calc"}


# --- schema/backward-compat -------------------------------------------------
def test_legacy_case_normalization():
    legacy = {"id": "x", "query": "y", "expected_sequence": ["rag", "calculator"],
              "required_operations": ["rag_pto_lookup", "subtraction_calculation"]}
    n = normalize_case(legacy)
    assert n["acceptable_tool_sequences"] == [["rag", "calculator"]]
    assert set(n["required_tools"]) == {"rag", "calculator"}
    ops_tools = [o.get("source") or o.get("tool") for o in n["operations"]]
    assert ops_tools == ["rag", "calculator"]   # derived from legacy op names


def test_number_parsing_normalization():
    a = extract_numbers("The total is $1,235.26")
    b = extract_numbers("1235.26")
    assert numbers_equal(a[0], b[0])
    assert extract_numbers("0.5% equals 613,521") == [0.5, 613521]


def test_taxonomy_precedence_answer_over_nothing():
    # everything fine except wrong final value
    primary, secondary = classify_failure_v2(
        execution_status="completed", task_completion={"complete": True},
        sequence_ok=True, selection_ok=True, arg_problems=None,
        answer_correct=False, faithfulness=None, utilization={"rate": 1.0})
    assert primary == "ANSWER_CORRECTNESS_FAILURE"
    assert secondary == [] or secondary == ["ANSWER_CORRECTNESS_FAILURE"]


def test_composite_renormalizes_on_na():
    c = composite_score({"correctness": 1.0, "task_completion": 0.5,
                         "groundedness": None, "utilization": None})
    assert abs(c["score"] - (0.4 * 1.0 + 0.3 * 0.5) / 0.7) < 1e-3
    assert c["label"].startswith("project-defined")


def test_claim_splitter_basic():
    claims = split_claims("PTO is 20 days. Sick leave is capped at 10 days!")
    assert len(claims) == 2
