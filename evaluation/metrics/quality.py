"""
Phase 4: Answer Quality & Task Completion Metrics (deterministic layer)
=======================================================================

Design principles:
- Ground-truth schema is RICH but BACKWARD COMPATIBLE: legacy datasets that
  only declare expected_sequence keep working via normalization.
- "Task Completion" measures whether the REQUIRED OPERATIONS actually
  happened and produced the needed information. It is deliberately
  independent of the exact tool sequence.
- "Acceptable sequences" lets ground truth declare multiple valid
  implementations of a task; nothing here hard-codes benchmark cases.
- Everything in this module is deterministic and unit-testable without an LLM.
"""

import re
from statistics import mean

# ---------------------------------------------------------------------------
# Number normalization helpers (shared by grounding + correctness layers)
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")

_STOP = set("""a an the is are was were be been being to of for in on at by with from as
and or if then than that this these those it its their our your you we they he she
per about into over under between within per""".split())


def _parse_number(tok: str):
    t = tok.strip().rstrip("%").replace("$", "").replace(",", "")
    if not t or t in ("-", "."):
        return None
    try:
        v = float(t)
        return int(v) if v == int(v) else v
    except ValueError:
        return None


def extract_numbers(text: str) -> list[float]:
    """Extract numeric values from text, normalizing commas/currency/percent."""
    out = []
    for m in _NUM_RE.findall(text or ""):
        v = _parse_number(m)
        if v is not None:
            out.append(v)
    return out


def numbers_equal(a, b, rel_tol=0.02) -> bool:
    """Tolerant equality: exact ints, 2% relative band otherwise."""
    try:
        if a == b:
            return True
        denom = max(abs(float(a)), abs(float(b)))
        return abs(float(a) - float(b)) / denom <= rel_tol
    except (TypeError, ZeroDivisionError):
        return False


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP]


# ---------------------------------------------------------------------------
# Ground truth schema normalization (backward compatible)
# ---------------------------------------------------------------------------

# Legacy required_operations strings -> operation objects
_CALC_HINTS = ("calculation", "calculate", "arithmetic", "math", "percent", "diff",
               "ratio", "subtraction", "multiplication", "division", "sqrt")
_LOOKUP_HINTS = ("search", "lookup", "population", "gdp", "price", "ceo", "news",
                 "speed", "height", "distance", "factual", "financial", "live")


def normalize_case(case: dict) -> dict:
    """Normalize any phase2/3/3B/4 case into the rich Phase 4 schema.

    Backward compatibility rules:
    - acceptable_tool_sequences defaults to [expected_sequence]
    - required_tools defaults to the set(expected_sequence)
    - operations are derived from legacy required_operations strings when absent
    """
    seq = case.get("expected_sequence")
    if seq is None:
        # No canonical path declared: treat the first acceptable sequence as
        # the reference for exact-sequence tracking (explicit [] stays []).
        acceptable_declared = case.get("acceptable_tool_sequences") or []
        seq = list(acceptable_declared[0]) if acceptable_declared else []
    ops = case.get("operations")
    if ops is None:
        ops = []
        for op in case.get("required_operations", []):
            o = str(op).lower()
            if any(h in o for h in _CALC_HINTS):
                ops.append({"tool": "calculator"})
            elif any(h in o for h in _LOOKUP_HINTS):
                # Legacy strings carry no coverage info; one execution satisfies.
                if "rag" in o:
                    ops.append({"source": "rag"})
                else:
                    ops.append({"tool": "web_search"})
            elif "memory" in o:
                ops.append({"source": "memory"})

    required_tools = case.get("required_tools",
                              sorted(set(seq)) if seq else [])
    acceptable = case.get("acceptable_tool_sequences",
                          [seq] if seq else [])

    return {
        "id": case["id"],
        "query": case["query"],
        "category": case.get("category", "uncategorized"),
        "expected_answer": case.get("expected_answer"),
        "expected_answer_range": case.get("expected_answer_range"),
        "required_information": case.get("required_information", []),
        "operations": ops,
        "required_tools": required_tools,
        "acceptable_tool_sequences": acceptable,
        "forbidden_tools": case.get("forbidden_tools", []),
        "arg_constraints": case.get("arg_constraints", []),
        "forbidden_in_answer": case.get("forbidden_in_answer", []),
        "expected_context": case.get("expected_context", []),
        "ground_truth_source": case.get("ground_truth_source", ""),
        "notes": case.get("notes", ""),
        # originals preserved for reporting/regression comparability
        "expected_sequence": seq,
        "_legacy": {k: case[k] for k in ("required_operations", "requires_multi_step")
                    if k in case},
    }


# ---------------------------------------------------------------------------
# Acceptable tool sequences
# ---------------------------------------------------------------------------

def evaluate_acceptable_sequences(acceptable_seqs: list, actual_seq: list) -> dict:
    """PASS if actual matches ANY declared acceptable sequence exactly."""
    if not acceptable_seqs:
        return {"applicable": False, "match": None}
    match = any(list(s) == list(actual_seq) for s in acceptable_seqs)
    return {"applicable": True, "match": match,
            "accepted": [list(s) for s in acceptable_seqs]}


# ---------------------------------------------------------------------------
# Task completion (operation/evidence based — NOT sequence based)
# ---------------------------------------------------------------------------

def _tool_results_for(tool_results: list, tool: str) -> list[dict]:
    return [r for r in tool_results or [] if r.get("tool") == tool]


def _covers_terms(haystacks: list[str], terms: list[str]) -> bool:
    if not terms:
        return True
    blob = " ".join(str(h) for h in haystacks).lower()
    return all(t.lower() in blob for t in terms)


def evaluate_task_completion(case_norm: dict, actual_seq: list,
                             tool_results: list, rag_context: str,
                             final_answer: str) -> dict:
    """Every declared operation must be satisfied by real evidence.

    Operation kinds:
      {"tool": "<tool>", "must_cover": [terms]?}  -> tool ran AND its output
                                                     covers the terms (if given).
      {"source": "rag"}                           -> RAG retrieval produced context.
      {"source": "memory"}                        -> memory route/retrieval engaged.
      {"answer_contains_any": [regex/strings]}    -> final answer carries the info.
    Coverage may be satisfied across MULTIPLE executions of the same tool
    (e.g. one combined search covering both entities counts once satisfied).
    """
    ops = case_norm.get("operations") or []
    if not ops:
        # Nothing richer declared: fall back to "required tools executed".
        req = case_norm.get("required_tools") or []
        missing = [t for t in req if t not in actual_seq]
        return {"applicable": bool(req), "complete": not missing,
                "missing": missing, "satisfied": [], "details": {}}

    satisfied, missing, details = [], [], {}
    for i, op in enumerate(ops):
        oid = op.get("op_id") or f"op_{i+1}"
        if op.get("source") == "rag":
            ok = bool(rag_context and len(rag_context.strip()) > 30)
        elif op.get("source") == "memory":
            ok = ("memory_search" in actual_seq) or bool(rag_context)
        elif op.get("answer_contains_any"):
            ok = any(re.search(p, final_answer or "", re.I)
                     for p in op["answer_contains_any"])
        else:
            tool = op.get("tool")
            results = _tool_results_for(tool_results, tool)
            if not results:
                ok = False
            elif op.get("must_cover"):
                outputs = [str(r.get("result", "")) for r in results]
                args_blob = " ".join(str(r.get("arguments", "")) for r in results)
                ok = _covers_terms(outputs + [args_blob], op["must_cover"])
            else:
                ok = all(not str(r.get("result", "")).startswith("Error")
                         for r in results)

        (satisfied if ok else missing).append(oid)
        details[oid] = ok

    complete = not missing
    return {"applicable": True, "complete": complete, "missing": missing,
            "satisfied": satisfied, "details": details}


# ---------------------------------------------------------------------------
# Tool-grounded answer correctness (deterministic, value-based)
# ---------------------------------------------------------------------------

def evaluate_tool_grounded(final_answer: str, tool_results: list,
                           context: str, tools_required: bool,
                           query: str | None = None) -> dict:
    """Do the load-bearing VALUES in the final answer trace back to evidence?

    Evidence = tool result texts + retrieved context. A number in the answer
    is grounded if it appears (normalized) in evidence. Values already present
    in the user's own query are given inputs, not claims, so they are exempt.
    Text claims are left to the judge; this layer catches the classic
    failure: calculator says 625000, answer says 6,250,000.
    """
    if not tools_required:
        return {"applicable": False}

    answer_nums = extract_numbers(final_answer or "")
    if not answer_nums:
        return {"applicable": True, "pass": None, "score": None,
                "ungrounded": [], "note": "no numeric claims in answer"}

    evidence_blob = " ".join(
        [str(r.get("result", "")) + " " + str(r.get("arguments", ""))
         for r in (tool_results or [])] + [context or ""])
    evidence_nums = extract_numbers(evidence_blob)
    query_nums = set(extract_numbers(query)) if query else set()

    ungrounded = []
    for v in answer_nums:
        if any(numbers_equal(v, q) for q in query_nums):
            continue  # echoed user-provided value: exempt
        if not any(numbers_equal(v, e) for e in evidence_nums):
            ungrounded.append(v)

    score = 1.0 - len(ungrounded) / len(answer_nums) if answer_nums else 1.0
    return {"applicable": True, "pass": not ungrounded, "score": round(score, 3),
            "ungrounded": ungrounded}


# ---------------------------------------------------------------------------
# Tool result utilization
# ---------------------------------------------------------------------------

def evaluate_utilization(case_norm: dict, tool_results: list,
                         rag_context: str, final_answer: str,
                         task_completion: dict) -> dict:
    """Were the important outputs of required tools actually USED downstream?

    An output counts as used when its key values/terms surface either in a
    subsequent tool's arguments (chaining) or in the final answer.
    """
    ops = case_norm.get("operations") or []
    if not ops:
        return {"applicable": False}

    used, unused = [], []
    for i, op in enumerate(ops):
        oid = op.get("op_id") or f"op_{i+1}"
        tool = op.get("tool")

        if op.get("source") in ("rag", "memory"):
            # Used iff the final answer draws on context (non-trivial overlap)
            cw = content_words(final_answer or "")
            ctx_words = set(content_words(rag_context or ""))
            overlap = sum(1 for w in cw[:60] if w in ctx_words)
            (used if overlap >= 3 else unused).append(oid)
            continue

        results = _tool_results_for(tool_results, tool)
        if not results:
            continue  # absence already penalized by task completion

        # later arguments that chain from this op
        later_args = " ".join(
            str(r.get("arguments", "")) for r in (tool_results or [])[i+1:])
        key_terms = op.get("must_cover") or []
        out_text = " ".join(str(r.get("result", "")) for r in results)
        out_nums = extract_numbers(out_text)

        used_here = False
        if key_terms:
            # Downstream may reuse either the key terms or the result's values.
            used_here = _covers_terms([later_args, final_answer], key_terms)
        out_nums = extract_numbers(out_text)
        if not used_here:
            if out_nums:
                ans_nums = extract_numbers((final_answer or "") + " " + later_args)
                used_here = any(numbers_equal(a, b) for a in ans_nums for b in out_nums)
            elif not key_terms:
                # textual result: content-word overlap with downstream usage
                ow = set(content_words(out_text))
                downstream = content_words((final_answer or "") + " " + later_args)[:80]
                used_here = sum(1 for w in downstream if w in ow) >= 2

        (used if used_here else unused).append(oid)

    total = len(used) + len(unused)
    rate = len(used) / total if total else None
    return {"applicable": True, "rate": round(rate, 3) if rate is not None else None,
            "used": used, "unused": unused}


# ---------------------------------------------------------------------------
# Failure taxonomy v2
# ---------------------------------------------------------------------------

_INFRA_SIGNATURES = ("dns error", "connecterror", "connection error", "timed out",
                     "timeout", "temporarily unavailable", "rate limit", "429",
                     "ssl", "getaddrinfo")


def classify_failure_v2(state_error=None, execution_status=None,
                        exec_trace=None, tool_results=None,
                        rag_required=False, rag_context="",
                        task_completion=None, sequence_ok=None,
                        selection_ok=None, arg_problems=None,
                        answer_correct=None, faithfulness=None,
                        utilization=None, forbidden_used=None) -> tuple[str, list]:
    """Return (primary_failure_or_None, secondary_failures[]).

    Precedence: infrastructure > evaluation > planner/tool-exec > retrieval >
    orchestration (premature/sequence/selection/args) > utilization >
    correctness > faithfulness.
    """
    primary, secondary = None, []

    err = (state_error or "")
    err_l = err.lower()
    status = execution_status or ""

    # 1. Infrastructure
    if state_error and any(s in err_l for s in _INFRA_SIGNATURES):
        return "INFRASTRUCTURE_FAILURE", []
    if state_error:
        primary = primary or "EVALUATION_FAILURE"

    # 2. Planner-level breakdowns recorded by the graph itself
    if status == "repeated_tool_call":
        secondary.append("PLANNER_FAILURE")
        primary = primary or "PREMATURE_TERMINATION"
    elif status == "error":
        primary = primary or "EVALUATION_FAILURE"

    # 3. Tool execution errors
    bad_tools = [r for r in (tool_results or [])
                 if str(r.get("result", "")).startswith("Error")]
    if bad_tools:
        sec = "TOOL_EXECUTION_FAILURE"
        secondary.append(sec)
        primary = primary or sec

    # 4. Retrieval failure (RAG required but empty)
    if rag_required and not (rag_context and len(rag_context.strip()) > 30):
        secondary.append("RETRIEVAL_FAILURE")
        primary = primary or "RETRIEVAL_FAILURE"

    # 5. Orchestration
    if task_completion is not None and not task_completion.get("complete", True):
        secondary.append("PREMATURE_TERMINATION")
        primary = primary or "PREMATURE_TERMINATION"
    if sequence_ok is False:
        secondary.append("WRONG_SEQUENCE")
        primary = primary or "WRONG_SEQUENCE"
    if selection_ok is False:
        secondary.append("TOOL_SELECTION_FAILURE")
        primary = primary or "TOOL_SELECTION_FAILURE"
    if arg_problems:
        secondary.append("TOOL_ARGUMENT_FAILURE")
        primary = primary or "TOOL_ARGUMENT_FAILURE"
    if forbidden_used:
        secondary.append("TOOL_SELECTION_FAILURE")
        primary = primary or "TOOL_SELECTION_FAILURE"

    # 6. Utilization
    if utilization and utilization.get("rate") is not None and utilization["rate"] < 0.99:
        secondary.append("TOOL_RESULT_UTILIZATION_FAILURE")
        primary = primary or "TOOL_RESULT_UTILIZATION_FAILURE"

    # 7. Answer-level
    if answer_correct is not None and not answer_correct:
        secondary.append("ANSWER_CORRECTNESS_FAILURE")
        primary = primary or "ANSWER_CORRECTNESS_FAILURE"
    if faithfulness is not None and not faithfulness:
        secondary.append("FAITHFULNESS_FAILURE")
        primary = primary or "FAITHFULNESS_FAILURE"

    if primary is None:
        return None, sorted(set(secondary))
    return primary, sorted(set(s for s in secondary if s != primary))


# ---------------------------------------------------------------------------
# Composite score (PROJECT-DEFINED, weights configurable)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "correctness": 0.40,
    "task_completion": 0.30,
    "groundedness": 0.20,
    "utilization": 0.10,
}


def composite_score(components: dict, weights: dict | None = None) -> dict:
    """Weighted mean over AVAILABLE components (N/A components are excluded
    and remaining weights renormalized). Every component stays visible
    separately in reports — this never hides individual metrics."""
    w = dict(weights or DEFAULT_WEIGHTS)
    num, den = 0.0, 0.0
    used = {}
    for k, weight in w.items():
        v = components.get(k)
        if v is None:
            continue
        num += weight * v
        den += weight
        used[k] = v
    score = num / den if den else None
    return {"score": round(score, 4) if score is not None else None,
            "components": used, "weights_effective": w,
            "label": "project-defined composite score"}
