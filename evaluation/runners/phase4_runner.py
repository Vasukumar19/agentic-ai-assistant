"""
Phase 4 benchmark runner: Answer Quality & Task Completion
==========================================================

Runs a dataset through the full agent graph and evaluates EVERY case on:
tool selection / exact sequence / declared-acceptable sequence /
task completion (operation-based) / answer correctness (deterministic +
structured LLM judge) / tool-grounded correctness / RAG faithfulness
(judge + deterministic claim cross-check) / tool result utilization /
composite score / failure taxonomy v2.

Usage:
  python evaluation/runners/phase4_runner.py \
      --dataset evaluation/datasets/phase4_quality_100.json [--limit N]
"""

import argparse
import json
import os
import re
import shutil
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("--dataset", default="evaluation/datasets/phase4_quality_100.json")
parser.add_argument("--limit", type=int, default=None)
parser.add_argument("--out", default=None, help="results file override")
args = parser.parse_args()

# Legacy runners parse CLI args at their module level; hide ours during import.
sys.argv = [sys.argv[0]]

from graph import create_runnable_graph
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
    is_absence_answer,
)
from evaluation.metrics.judge import AnswerJudge, deterministic_faithfulness
from evaluate_phase3_live import extract_planner_trace

MEMORY_DIR = Path("memory")
_INFRA_RE = re.compile(r"dns|connecterror|connection error|timed out|timeout|rate limit|429", re.I)


def looks_infra(exc_text: str) -> bool:
    return bool(_INFRA_RE.search(exc_text or ""))


def _check_arg_constraints(constraints, tool_results):
    """Validate declared argument constraints against executed tool args."""
    problems = []
    for c in constraints or []:
        execs = [r for r in tool_results if r.get("tool") == c["tool"]]
        if not execs:
            problems.append(f"{c['tool']} never ran")
            continue
        ok_any = False
        for r in execs:
            arg_blob = json.dumps(r.get("arguments", {}))
            all_ok = all(tok.lower() in arg_blob.lower() for tok in c.get("must_include_all", []))
            any_ok = (not c.get("must_include_any")) or any(
                tok.lower() in arg_blob.lower() for tok in c["must_include_any"])
            if all_ok and any_ok:
                ok_any = True
                break
        if not ok_any:
            problems.append(f"{c['tool']} args violated constraint {c}")
    return problems


def _forbidden_used(case_norm, actual_seq):
    return sorted(set(actual_seq) & set(case_norm["forbidden_tools"]))


def _deterministic_correctness(ans: str, exp, rng, req_info):
    """Returns (decisive, ok, score, details)."""
    details = {}
    ans_nums = extract_numbers(ans or "")

    numeric_ok = None
    if rng:
        lo, hi = rng
        numeric_ok = any(lo <= n <= hi for n in ans_nums)
        details["numeric"] = f"in-range={numeric_ok}"
        decisive_numeric = True
    elif isinstance(exp, str) and extract_numbers(exp):
        exp_nums = extract_numbers(exp)
        numeric_ok = any(numbers_equal(a, e) for a in ans_nums for e in exp_nums)
        details["numeric"] = f"match={numeric_ok}"
        decisive_numeric = True
    else:
        decisive_numeric = False

    # required information tokens
    info_ok, info_missing = True, []
    for item in req_info or []:
        it = str(item)
        if it.lower() in (ans or "").lower():
            continue
        item_nums = extract_numbers(it)
        if item_nums and all(any(numbers_equal(a, e) for a in ans_nums) for e in item_nums):
            continue
        info_ok = False
        info_missing.append(it)

    forbidden_hit = None  # filled by caller via forbidden_in_answer

    if decisive_numeric:
        ok = bool(numeric_ok) and info_ok
        score = 1.0 if ok else (0.5 if info_ok else 0.25 if numeric_ok else 0.0)
        return True, ok, round(score, 3), {**details, "info_missing": info_missing}
    return False, info_ok, (1.0 if info_ok else 0.0), {**details, "info_missing": info_missing}


def evaluate_case(app, judge, raw_case, rid):
    case = normalize_case(raw_case)

    # template run-id into query/answers for memory isolation
    def tpl(s):
        return s.replace("{rid}", rid) if isinstance(s, str) else s
    question = tpl(raw_case["query"])
    exp_answer = tpl(raw_case.get("expected_answer")) if raw_case.get("expected_answer") else None

    t0 = time.perf_counter()
    state_error, state = None, {}
    try:
        state = app.invoke({"question": question})
    except Exception as exc:
        state_error = str(exc)
    total_latency = time.perf_counter() - t0

    out = {
        "id": case["id"], "category": case["category"], "query": question,
        "latency_s": round(total_latency, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if state_error:
        primary = "INFRASTRUCTURE_FAILURE" if looks_infra(state_error) else "EVALUATION_FAILURE"
        out.update({"error": state_error[:300], "primary_failure": primary,
                    "status": "error"})
        return out

    trace = extract_planner_trace(state)
    actual_seq = trace["actual_sequence"]
    tool_results = [
        {"tool": tr.get("tool"), "arguments": tr.get("args"),
         "result": str(tr.get("output") or "")[:2000]}
        for tr in trace["arg_trace"]]
    rag_context = state.get("_combined_context", "") or state.get("rag_context", "")
    final_answer = state.get("answer", "") or ""
    execution_trace = state.get("execution_trace", [])
    planner_calls = sum(1 for t in execution_trace if str(t.get("step", "")).startswith("planner"))

    # --- orchestration metrics --------------------------------------------
    # Selection measures PLANNER tool choices. Pre-retrieval steps (rag /
    # memory_search) are graph nodes, not planner decisions; their presence
    # is governed by task completion / operations, not by this metric.
    _PRE_TOOLS = {"rag", "memory_search"}
    planner_tools = [t for t in actual_seq if t not in _PRE_TOOLS]
    forb = _forbidden_used(case, actual_seq)
    sel_ok = set(planner_tools) == set(case["required_tools"])
    seq_exact = list(case["expected_sequence"]) == list(actual_seq)
    acc = evaluate_acceptable_sequences(case["acceptable_tool_sequences"], actual_seq)
    # memory engagement: explicit recall step OR memory_update route handled
    # the write/recall (no planner tools ran and we got an answer back).
    mem_ops = [o for o in case["operations"] if o.get("source") == "memory"]
    memory_engaged = ("memory_search" in actual_seq) or (
        bool(mem_ops) and not planner_tools and bool(final_answer))
    tc = evaluate_task_completion(case, actual_seq, tool_results, rag_context,
                                  final_answer, memory_engaged=memory_engaged)

    arg_problems = _check_arg_constraints(case["arg_constraints"], tool_results)

    # --- answer-level metrics ----------------------------------------------
    det_decisive, det_ok, det_score, det_details = _deterministic_correctness(
        final_answer, exp_answer, raw_case.get("expected_answer_range"),
        [tpl(r) for r in case["required_information"]])

    forbidden_violation = any(re.search(p, final_answer or "", re.I)
                              for p in case["forbidden_in_answer"])

    judge_meta, judge_verdict = None, None
    need_judge = (not det_decisive) and exp_answer is not None
    if need_judge:
        try:
            jr = judge.judge_answer(question, exp_answer, final_answer,
                                    case["required_information"],
                                    evidence=(rag_context + "\n" +
                                              "\n".join(str(r.get("result")) for r in tool_results))[:4000])
            judge_verdict, judge_meta = jr["verdict"], jr["meta"]
        except Exception as exc:
            judge_verdict = {"error": str(exc)[:200]}

    if forbidden_violation:
        answer_correct, correctness_score = False, 0.0
    elif det_decisive:
        answer_correct, correctness_score = det_ok, det_score
    elif judge_verdict and "error" not in judge_verdict:
        answer_correct = bool(judge_verdict["correct"])
        correctness_score = float(judge_verdict["score"])
    else:
        answer_correct, correctness_score = det_ok, det_score

    tools_required = bool(case["required_tools"]) or bool(
        [o for o in case["operations"] if o.get("tool")])
    grounding = evaluate_tool_grounded(final_answer, tool_results, rag_context,
                                       tools_required, query=question)

    # --- RAG faithfulness ----------------------------------------------------
    faith_judge, faith_det, faith_pass = None, None, None
    absence_answer = is_absence_answer(final_answer)
    if (rag_context and len(rag_context.strip()) > 30 and final_answer
            and not absence_answer):
        faith_det = deterministic_faithfulness(rag_context, final_answer)
        if case["category"] in ("answer_grounded", "rag_memory", "adversarial") or "rag" in actual_seq:
            try:
                fj = judge.judge_faithfulness(question, rag_context, final_answer)
                faith_judge, judge_meta = fj["verdict"], fj["meta"]
                faith_pass = (faith_judge["faithfulness_score"] >= 0.99
                              and not faith_judge["contradictions"])
            except Exception as exc:
                faith_judge = {"error": str(exc)[:200]}
                faith_pass = None

    util = evaluate_utilization(case, tool_results, rag_context, final_answer, tc)

    # --- composite + taxonomy -------------------------------------------------
    comp = composite_score({
        "correctness": correctness_score if exp_answer is not None else None,
        "task_completion": 1.0 if (tc["complete"] if tc["applicable"] else sel_ok) else 0.0,
        "groundedness": grounding.get("score"),
        "utilization": util.get("rate"),
    })

    sequence_ok_effective = (acc["match"] if acc["applicable"] else seq_exact)
    # RAG is a *mandatory* step only when every acceptable sequence needs it;
    # optional-rag cases must not be flagged RETRIEVAL_FAILURE for skipping it.
    acc_seqs = [list(s) for s in case["acceptable_tool_sequences"] if s]
    rag_mandatory = bool(acc_seqs) and all("rag" in s for s in acc_seqs)

    primary_failure, secondary_failures = classify_failure_v2(
        state_error=None, execution_status=state.get("execution_status"),
        exec_trace=execution_trace, tool_results=tool_results,
        rag_required=rag_mandatory,
        rag_context=rag_context, task_completion=tc if tc["applicable"] else None,
        sequence_ok=sequence_ok_effective, selection_ok=sel_ok if case["required_tools"] else None,
        arg_problems=arg_problems, answer_correct=(None if exp_answer is None else answer_correct),
        faithfulness=faith_pass, utilization=util if util["applicable"] else None,
        forbidden_used=forb)

    out.update({
        "actual_sequence": actual_seq,
        "expected_sequence": case["expected_sequence"],
        "acceptable_sequences": case["acceptable_tool_sequences"],
        "selection_ok": sel_ok,
        "sequence_exact": seq_exact,
        "sequence_acceptable": sequence_ok_effective,
        "task_completion": tc,
        "final_answer": final_answer[:800],
        "expected_answer": exp_answer,
        "answer_correct": answer_correct if exp_answer is not None else None,
        "correctness_score": correctness_score if exp_answer is not None else None,
        "correctness_details": {**det_details,
                                "judge": judge_verdict,
                                "forbidden_violation": forbidden_violation},
        "grounding": grounding,
        "faithfulness_deterministic": faith_det,
        "faithfulness_judge": faith_judge,
        "faithfulness_pass": faith_pass,
        "utilization": util,
        "arg_problems": arg_problems,
        "forbidden_tools_used": forb,
        "planner_calls_actual": planner_calls,
        "llm_calls": trace["llm_calls"],
        "tool_call_count": trace["tool_call_count"],
        "execution_status": state.get("execution_status"),
        "rag_context_chars": len(rag_context),
        "rag_context_excerpt": rag_context[:1500],
        "tool_results": tool_results[:6],
        "composite": comp,
        "primary_failure": primary_failure,
        "secondary_failures": secondary_failures,
        "judge_meta": judge_meta,
        "status": "completed",
    })
    return out


def aggregate(results):
    done = [r for r in results if r.get("status") == "completed"]
    n = len(done)
    if not n:
        return {}

    def frac(pred):
        return sum(1 for r in done if pred(r)) / n

    lat = sorted(r["latency_s"] for r in done)

    def na_mean(key):
        vals = [r[key] for r in done if r.get(key) is not None]
        return round(statistics.mean(vals), 4) if vals else None

    comp_scores = [r["composite"]["score"] for r in done if r["composite"]["score"] is not None]
    util_vals = [r["utilization"]["rate"] for r in done
                 if r.get("utilization", {}).get("rate") is not None]

    fail_counts = {}
    for r in done + [x for x in results if x.get("status") == "error"]:
        p = r.get("primary_failure")
        if p:
            fail_counts[p] = fail_counts.get(p, 0) + 1

    return {
        "n_total": len(results), "n_completed": n,
        "tool_selection_acc": frac(lambda r: r["selection_ok"]),
        "exact_sequence_acc": frac(lambda r: r["sequence_exact"]),
        "acceptable_sequence_acc": frac(lambda r: r["sequence_acceptable"]),
        "task_completion_rate": frac(lambda r: r["task_completion"].get("complete", True)),
        "answer_correctness": na_mean("answer_correct"),
        "mean_correctness_score": na_mean("correctness_score"),
        "tool_grounded_acc": frac(lambda r: r["grounding"].get("pass") is not False
                                  if r["grounding"].get("applicable") else True),
        "faithfulness_acc": frac(lambda r: r.get("faithfulness_pass") is not False
                                 if r.get("faithfulness_pass") is not None else True),
        "utilization_rate": round(statistics.mean(util_vals), 4) if util_vals else None,
        "premature_orchestration_fail": frac(lambda r: "PREMATURE_TERMINATION" in r.get("secondary_failures", []) or r.get("primary_failure") == "PREMATURE_TERMINATION"),
        "unnecessary_tool_fail": frac(lambda r: bool(r.get("forbidden_tools_used")) or r.get("primary_failure") == "TOOL_SELECTION_FAILURE"),
        "infrastructure_failures": sum(1 for r in results if r.get("primary_failure") == "INFRASTRUCTURE_FAILURE"),
        "failure_taxonomy": fail_counts,
        "mean_composite": round(statistics.mean(comp_scores), 4) if comp_scores else None,
        "mean_latency_s": round(statistics.mean(lat), 2),
        "p50_latency_s": round(statistics.median(lat), 2),
        "p95_latency_s": round(lat[int(len(lat) * 0.95)], 2),
        "avg_llm_calls": round(statistics.mean(r["llm_calls"] for r in done), 2),
        "avg_tool_calls": round(statistics.mean(r["tool_call_count"] for r in done), 2),
    }


def main():
    dataset_path = Path(args.dataset)
    raw_cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    if args.limit:
        raw_cases = raw_cases[:args.limit]

    rid = uuid.uuid4().hex[:6]
    print(f"=== Phase 4 Answer Quality Benchmark ===")
    print(f"Dataset: {dataset_path} | Cases: {len(raw_cases)} | Run ID: {rid}")

    # Snapshot memory dir so eval writes don't permanently pollute user state
    mem_backup = None
    if MEMORY_DIR.exists():
        mem_backup = Path(os.environ.get("TEMP", "/tmp")) / f"mem_backup_{uuid.uuid4().hex[:8]}"
        shutil.copytree(MEMORY_DIR, mem_backup)

    app = create_runnable_graph()
    judge = AnswerJudge()

    results, retried = [], []
    for i, case in enumerate(raw_cases):
        cid = case["id"]
        try:
            res = evaluate_case(app, judge, case, rid)
        except Exception as exc:
            res = {"id": cid, "status": "error",
                   "error": str(exc)[:250],
                   "primary_failure": "INFRASTRUCTURE_FAILURE" if looks_infra(str(exc))
                   else "EVALUATION_FAILURE"}
        results.append(res)
        mark = res.get("primary_failure") or "OK"
        extra = f" | retrying infra..." if res.get("status") == "error" and looks_infra(res.get("error", "")) else ""
        print(f"[{i+1}/{len(raw_cases)}] {cid}: {mark} "
              f"(seq={res.get('actual_sequence')}, tc={res.get('task_completion', {}).get('complete', '-')}, "
              f"ans={res.get('answer_correct', '-')}, lat={res.get('latency_s')}s){extra}")

        # one automatic retry for infrastructure flakes
        if res.get("status") == "error" and looks_infra(res.get("error", "")):
            time.sleep(3)
            try:
                res2 = evaluate_case(app, judge, case, rid)
                if res2.get("status") != "error":
                    results[-1] = res2
                    retried.append(cid)
                    print(f"    -> retry OK ({cid})")
            except Exception:
                pass

    if mem_backup:
        shutil.rmtree(MEMORY_DIR, ignore_errors=True)
        shutil.move(str(mem_backup), str(MEMORY_DIR))

    m = aggregate(results)
    print("\n── Phase 4 Aggregate ──")
    for k, v in m.items():
        if isinstance(v, float) and v <= 1.0 and (
                "acc" in k or "rate" in k or "completion" in k or "correctness" in k or "faithfulness" in k):
            print(f"  {k}: {v*100:.1f}%")
        else:
            print(f"  {k}: {v}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out or f"evaluation/results/phase4_quality_{stamp}.json")
    out_path.write_text(json.dumps({
        "run_id": rid, "dataset": str(dataset_path),
        "retried_cases": retried,
        "aggregate": m, "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
