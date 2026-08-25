"""
Recompute per-case derived metrics + aggregates for a saved Phase 4 results
file using CURRENT evaluator semantics (no agent re-execution).

Currently fixes:
- tool selection = set(planner tools) == set(required_tools), where pre-
  retrieval steps (rag/memory_search) are excluded from planner choices.
- failure taxonomy re-derived with the corrected selection signal.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

results_path = Path(sys.argv[1])
dataset_path = Path("evaluation/datasets/phase4_quality_100.json")

data = json.loads(results_path.read_text(encoding="utf-8"))
cases = {c["id"]: c for c in json.loads(dataset_path.read_text(encoding="utf-8"))}

from evaluation.metrics.quality import classify_failure_v2, is_absence_answer  # noqa: E402

_PRE = {"rag", "memory_search"}


def frac(pred, rows):
    return sum(1 for r in rows if pred(r)) / len(rows) if rows else None


for r in data["results"]:
    if r.get("status") != "completed":
        continue
    case = cases[r["id"]]
    required_tools = case.get("required_tools", [])
    actual = r["actual_sequence"]
    planner_tools = [t for t in actual if t not in _PRE]
    forb_used = bool(set(actual) & set(case.get("forbidden_tools", [])))
    r["selection_ok"] = (set(planner_tools) == set(required_tools)
                         and not forb_used)

    # memory engagement (mirrors phase4_runner)
    mem_ops = [o for o in case.get("operations", []) if o.get("source") == "memory"]
    memory_engaged = ("memory_search" in actual) or (
        bool(mem_ops) and not planner_tools
        and r.get("execution_status") == "completed" and bool(r.get("final_answer")))

    # recompute task completion with corrected semantics
    from evaluation.metrics.quality import normalize_case, evaluate_task_completion, evaluate_utilization  # noqa: E402
    nc = normalize_case(case)
    tc = evaluate_task_completion(nc, actual, r.get("tool_results", []),
                                  "x" * (50 if r.get("rag_context_chars", 0) > 30 else 0),
                                  r.get("final_answer", ""),
                                  memory_engaged=memory_engaged)
    r["task_completion"] = tc

    u = evaluate_utilization(nc, r.get("tool_results", []),
                             "x" * (50 if r.get("rag_context_chars", 0) > 30 else 0),
                             r.get("final_answer", ""), tc)
    if u.get("rate") is not None:
        r["utilization"] = u

    seq_eff = r.get("sequence_acceptable")
    acc_seqs = [list(s) for s in case.get("acceptable_tool_sequences", []) if s]
    rag_mandatory = bool(acc_seqs) and all("rag" in s for s in acc_seqs)
    absence_answer = is_absence_answer(r.get("final_answer", ""))
    primary, secondary = classify_failure_v2(
        state_error=None,
        execution_status=r.get("execution_status"),
        exec_trace=None,
        tool_results=r.get("tool_results", []),
        rag_required=rag_mandatory and r.get("rag_context_chars", 0) == 0,
        rag_context="x" * (50 if r.get("rag_context_chars", 0) > 30 else 0),
        task_completion=tc if tc.get("applicable") else None,
        sequence_ok=(None if seq_eff is None else seq_eff),
        selection_ok=(r["selection_ok"]
                      if (case.get("required_tools") or case.get("forbidden_tools"))
                      else None),
        arg_problems=r.get("arg_problems") or None,
        answer_correct=r.get("answer_correct"),
        faithfulness=(None if absence_answer else r.get("faithfulness_pass")),
        utilization=u if u.get("applicable") else None,
        forbidden_used=bool(r.get("forbidden_tools_used")),
    )
    r["primary_failure"], r["secondary_failures"] = primary, secondary

done = [r for r in data["results"] if r.get("status") == "completed"]
n = len(done)
lat = sorted(r["latency_s"] for r in done)


def na_mean(key):
    vals = [r[key] for r in done if isinstance(r.get(key), (int, float))]
    return round(statistics.mean(vals), 4) if vals else None


util_vals = [r["utilization"]["rate"] for r in done
             if r.get("utilization", {}).get("rate") is not None]
comp_scores = [r["composite"]["score"] for r in done
               if r["composite"]["score"] is not None]

fail_counts = {}
for r in data["results"]:
    p = r.get("primary_failure")
    if p:
        fail_counts[p] = fail_counts.get(p, 0) + 1

m = {
    "n_total": len(data["results"]), "n_completed": n,
    "tool_selection_acc": round(frac(lambda r: r["selection_ok"], done), 4),
    "exact_sequence_acc": round(frac(lambda r: r["sequence_exact"], done), 4),
    "acceptable_sequence_acc": round(frac(lambda r: r["sequence_acceptable"], done), 4),
    "task_completion_rate": round(frac(lambda r: r["task_completion"].get("complete", True), done), 4),
    "answer_correctness": na_mean("answer_correct"),
    "mean_correctness_score": na_mean("correctness_score"),
    "tool_grounded_acc": round(frac(lambda r: r["grounding"].get("pass") is not False
                                    if r["grounding"].get("applicable") else True, done), 4),
    "faithfulness_acc": round(frac(lambda r: r.get("faithfulness_pass") is not False
                                   if r.get("faithfulness_pass") is not None else True, done), 4),
    "utilization_rate": round(statistics.mean(util_vals), 4) if util_vals else None,
    "infrastructure_failures": sum(1 for r in data["results"]
                                   if r.get("primary_failure") == "INFRASTRUCTURE_FAILURE"),
    "failure_taxonomy": fail_counts,
    "mean_composite": round(statistics.mean(comp_scores), 4) if comp_scores else None,
    "mean_latency_s": round(statistics.mean(lat), 2),
    "p50_latency_s": round(statistics.median(lat), 2),
    "p95_latency_s": round(lat[int(len(lat) * 0.95)], 2),
    "avg_llm_calls": round(statistics.mean(r["llm_calls"] for r in done), 2),
    "avg_tool_calls": round(statistics.mean(r["tool_call_count"] for r in done), 2),
}
data["aggregate"] = m

out = results_path.with_name(results_path.stem + "_fixed.json")
out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"Fixed results -> {out}")
for k, v in m.items():
    if isinstance(v, float) and v <= 1.0 and (
            "acc" in k or "rate" in k or "completion" in k or "correctness" in k
            or "faithfulness" in k):
        print(f"  {k}: {v*100:.1f}%")
    else:
        print(f"  {k}: {v}")
