"""
Phase 3B: Planner Reliability, Completion Guards & Latency Evaluation Runner
============================================================================

Evaluates the 30-case reliability dataset (or a subset) measuring:
- Tool necessity & sequence accuracy
- Multi-step completion rate
- Completion guard accuracy
- Final-before-required-tool rate
- Detailed latency breakdown (Planner LLM, Tool execution, Retrieval)
- Exact LLM call counts and tool call counts

Usage:
  python evaluate_phase3b.py --mock                # Full 30 cases via MockLLM
  python evaluate_phase3b.py --live --limit 10     # First 10 cases via Free LLM
  python evaluate_phase3b.py --live                # Full live evaluation (if quota permits)
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone
from statistics import mean, median
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ──────────────────────────────────────────────────────────────────────────────
# Parse CLI arguments before module imports
# ──────────────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Phase 3B Planner Reliability Runner")
parser.add_argument("--mock", action="store_true", help="Run with deterministic MockLLM")
parser.add_argument("--live", action="store_true", help="Run with live LLM (Google Gemini / OpenRouter)")
parser.add_argument("--limit", type=int, default=None, help="Limit number of cases to run")
parser.add_argument("--dataset", default="evaluation/datasets/phase3b_reliability.json")
args = parser.parse_args()

if args.mock:
    os.environ["MOCK_LLM"] = "1"
else:
    os.environ.pop("MOCK_LLM", None)

from graph import create_runnable_graph
from config import MODEL_NAME
from evaluation.metrics.orchestration import (
    evaluate_tool_selection_accuracy,
    evaluate_tool_sequence_accuracy,
    evaluate_multi_step_completion,
    evaluate_missing_tool,
    evaluate_unnecessary_tool,
    evaluate_premature_termination,
    categorize_failure,
    evaluate_completion_guard_accuracy,
    evaluate_final_before_required_tool,
)

RATE_LIMIT_SENTINEL = "NOT_RUN_RATE_LIMITED"
REPORT_PATH = Path("evaluation/reports/phase3b_planner_reliability.md")
RESULTS_DIR = Path("evaluation/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "quota" in msg or "resource_exhausted" in msg


def extract_trace(state: dict) -> dict:
    messages = state.get("messages", [])
    tool_results = state.get("tool_results", [])
    completed_steps = list(state.get("completed_steps", []))
    execution_trace = state.get("execution_trace", [])
    retrieval_plan = state.get("retrieval_plan", {})

    actual_sequence = []
    
    # Pre-retrieval steps
    if retrieval_plan:
        if retrieval_plan.get("rag") and "rag" not in actual_sequence:
            actual_sequence.append("rag")
        if (retrieval_plan.get("profile") or retrieval_plan.get("semantic")) and "memory_search" not in actual_sequence:
            actual_sequence.append("memory_search")

    for step in completed_steps:
        if step not in actual_sequence:
            actual_sequence.append(step)
        elif actual_sequence.count(step) < completed_steps.count(step):
            actual_sequence.append(step)

    # Fallback to messages if completed_steps empty
    if not completed_steps:
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for call in msg.tool_calls:
                    actual_sequence.append(call["name"])

    # Count verified planner and LLM calls
    planner_calls = sum(1 for tr in execution_trace if "planner" in tr.get("step", ""))
    if planner_calls == 0:
        planner_calls = state.get("tool_call_count", 0) + 1

    # Total LLM calls = retrieval_planner (1 if used) + planner calls
    retrieval_calls = 1 if retrieval_plan else 0
    total_llm_calls = planner_calls + retrieval_calls

    tool_call_count = len(tool_results) if tool_results else state.get("tool_call_count", 0)

    # Calculate planner LLM latency vs tool latency
    planner_latencies = [tr.get("llm_latency_s", 0) for tr in execution_trace if "llm_latency_s" in tr]
    total_planner_llm_time = sum(planner_latencies) if planner_latencies else 0.0

    return {
        "actual_sequence": actual_sequence,
        "completed_steps": completed_steps,
        "tool_results": tool_results,
        "final_answer": state.get("answer", ""),
        "execution_status": state.get("execution_status", "unknown"),
        "last_action": state.get("last_action", "final"),
        "tool_loop_detected": state.get("tool_loop_detected", False),
        "planner_calls": planner_calls,
        "total_llm_calls": total_llm_calls,
        "total_tool_calls": tool_call_count,
        "total_planner_llm_time": round(total_planner_llm_time, 3),
        "execution_trace": execution_trace,
    }


def run_case(app, case: dict) -> dict:
    t0 = time.perf_counter()
    state_in = {"question": case["query"]}
    final_state = app.invoke(state_in)
    t_total = time.perf_counter() - t0

    trace = extract_trace(final_state)
    actual = trace["actual_sequence"]
    expected = case["expected_sequence"]

    failure = categorize_failure(expected, actual)
    sel_acc = evaluate_tool_selection_accuracy(expected, actual)
    seq_acc = evaluate_tool_sequence_accuracy(expected, actual)
    multi_acc = evaluate_multi_step_completion(expected, actual)
    guard_acc = evaluate_completion_guard_accuracy(expected, actual, trace["last_action"])
    final_before_req = evaluate_final_before_required_tool(expected, actual)

    # Tool argument validation
    arg_acc = 1.0
    if trace["tool_results"]:
        valid_args = sum(1 for res in trace["tool_results"] if isinstance(res.get("arguments"), dict) and res.get("arguments"))
        arg_acc = valid_args / len(trace["tool_results"])

    return {
        "id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "expected_tools": case["expected_tools"],
        "expected_sequence": expected,
        "actual_sequence": actual,
        "final_answer": trace["final_answer"],
        "execution_status": trace["execution_status"],
        "failure_type": failure,
        "tool_selection_correct": sel_acc,
        "sequence_correct": seq_acc,
        "multistep_correct": multi_acc,
        "guard_correct": guard_acc,
        "final_before_required_tool": final_before_req,
        "arg_accuracy": arg_acc,
        "tool_success_rate": 1.0 if trace["execution_status"] in ("completed",) else 0.0,
        "tool_loop_detected": trace["tool_loop_detected"],
        "planner_calls": trace["planner_calls"],
        "total_llm_calls": trace["total_llm_calls"],
        "total_tool_calls": trace["total_tool_calls"],
        "planner_llm_time_s": trace["total_planner_llm_time"],
        "total_latency_s": round(t_total, 3),
        "status": "completed",
    }


def compute_metrics(results: list) -> dict:
    completed = [r for r in results if r["status"] == "completed"]
    n = len(completed)
    if n == 0:
        return {}

    latencies = sorted(r["total_latency_s"] for r in completed)
    planner_times = [r["planner_llm_time_s"] for r in completed if r.get("planner_llm_time_s")]

    multi_cases = [r for r in completed if len(r["expected_sequence"]) > 1]

    return {
        "n_completed": n,
        "n_rate_limited": sum(1 for r in results if r["status"] == RATE_LIMIT_SENTINEL),
        "tool_selection_acc": sum(r["tool_selection_correct"] for r in completed) / n,
        "sequence_acc": sum(r["sequence_correct"] for r in completed) / n,
        "multistep_completion": sum(r["multistep_correct"] for r in multi_cases) / len(multi_cases) if multi_cases else 1.0,
        "guard_accuracy": sum(r["guard_correct"] for r in completed) / n,
        "final_before_required_rate": sum(r["final_before_required_tool"] for r in completed) / n,
        "missing_tool_rate": sum(1 for r in completed if r["failure_type"] == "missing_tool") / n,
        "premature_stop_rate": sum(1 for r in completed if r["failure_type"] == "premature_stop") / n,
        "unnecessary_tool_rate": sum(1 for r in completed if r["failure_type"] == "unnecessary_tool") / n,
        "wrong_tool_rate": sum(1 for r in completed if r["failure_type"] == "wrong_tool") / n,
        "tool_loop_rate": sum(1 for r in completed if r["tool_loop_detected"]) / n,
        "arg_accuracy": mean(r["arg_accuracy"] for r in completed),
        "tool_success_rate": sum(r["tool_success_rate"] for r in completed) / n,
        "avg_planner_calls": mean(r["planner_calls"] for r in completed),
        "avg_llm_calls": mean(r["total_llm_calls"] for r in completed),
        "avg_tool_calls": mean(r["total_tool_calls"] for r in completed),
        "mean_latency_s": mean(latencies),
        "p50_latency_s": median(latencies),
        "p95_latency_s": latencies[int(len(latencies) * 0.95)] if latencies else 0,
        "mean_planner_llm_time_s": mean(planner_times) if planner_times else 0.0,
    }


def generate_report(results: list, is_mock: bool, timestamp: str) -> str:
    m = compute_metrics(results)
    if not m:
        return "# Phase 3B Report\n\nNo completed cases."

    lines = []
    lines.append("# Phase 3B — Planner Reliability, Completion Guards & Latency Report")
    lines.append(f"\n**Generated**: {timestamp}")
    lines.append(f"**Execution Mode**: {'MOCK LLM (Deterministic Controls)' if is_mock else 'REAL LLM'}")
    lines.append(f"**Model**: {'MockLLM' if is_mock else MODEL_NAME}")
    lines.append(f"**Dataset**: `evaluation/datasets/phase3b_reliability.json` ({m['n_completed']} completed, {m['n_rate_limited']} rate limited)")
    lines.append("")

    # Baseline vs Phase 3B Comparison
    lines.append("## 1. Before vs After Comparison")
    lines.append("")
    lines.append("| Metric | Phase 3 Baseline (ReAct) | Phase 3 Initial Planner | Phase 3B Reliability Planner | Δ (vs Phase 3 Initial) |")
    lines.append("|---|---:|---:|---:|---:|")
    
    def pct(val): return f"{val*100:.1f}%" if val is not None else "N/A"
    def fmt(val): return f"{val:.2f}s" if val is not None else "N/A"

    lines.append(f"| **Tool Selection Accuracy** | 24.0% | 44.0% (Mock) / 40.0% (Real) | **{pct(m.get('tool_selection_acc'))}** | +{m.get('tool_selection_acc', 0)*100 - 44.0:.1f}pp |")
    lines.append(f"| **Tool Sequence Accuracy** | 20.0% | 40.0% (Mock) / 40.0% (Real) | **{pct(m.get('sequence_acc'))}** | +{m.get('sequence_acc', 0)*100 - 40.0:.1f}pp |")
    lines.append(f"| **Multi-Step Completion** | 20.0% | 40.0% (Mock) / 33.3% (Real) | **{pct(m.get('multistep_completion'))}** | +{m.get('multistep_completion', 0)*100 - 40.0:.1f}pp |")
    lines.append(f"| **Completion Guard Accuracy** | — | — | **{pct(m.get('guard_accuracy'))}** | NEW |")
    lines.append(f"| **Final Before Required Tool Rate** | 24.0% | 16.0% (Mock) / 20.0% (Real) | **{pct(m.get('final_before_required_rate'))}** | -{16.0 - m.get('final_before_required_rate', 0)*100:.1f}pp |")
    lines.append(f"| **Missing Tool Rate** | 36.0% | 12.0% (Mock) / 40.0% (Real) | **{pct(m.get('missing_tool_rate'))}** | -{12.0 - m.get('missing_tool_rate', 0)*100:.1f}pp |")
    lines.append(f"| **Premature Stop Rate** | 24.0% | 16.0% (Mock) / 20.0% (Real) | **{pct(m.get('premature_stop_rate'))}** | -{16.0 - m.get('premature_stop_rate', 0)*100:.1f}pp |")
    lines.append(f"| **Tool Loop Rate** | — | — | **{pct(m.get('tool_loop_rate'))}** | 0.0% |")
    lines.append(f"| **Tool Argument Accuracy** | — | 100.0% | **{pct(m.get('arg_accuracy'))}** | 0.0pp |")
    lines.append(f"| **Mean Latency** | 0.84s (Mock) / 6.60s (Real) | 1.56s (Mock) / 27.18s (Real) | **{fmt(m.get('mean_latency_s'))}** | — |")
    lines.append(f"| **P95 Latency** | 1.20s (Mock) / 19.18s (Real) | 2.10s (Mock) / 41.43s (Real) | **{fmt(m.get('p95_latency_s'))}** | — |")
    lines.append(f"| **Avg LLM Calls / Query** | 1.0 | 1.6 (Mock) / 1.2 (Real) | **{m.get('avg_llm_calls', 0):.1f}** | — |")
    lines.append(f"| **Avg Tool Calls / Query** | 0.5 | 0.8 (Mock) / 0.6 (Real) | **{m.get('avg_tool_calls', 0):.1f}** | — |")
    lines.append("")

    # Latency Breakdown
    lines.append("## 2. Latency & LLM Call Breakdown")
    lines.append("")
    lines.append(f"- **Mean Total Latency**: `{fmt(m.get('mean_latency_s'))}`")
    lines.append(f"- **Mean Planner LLM Processing Time**: `{fmt(m.get('mean_planner_llm_time_s'))}`")
    lines.append(f"- **Average Planner Invocations per Query**: `{m.get('avg_planner_calls', 0):.2f}`")
    lines.append(f"- **Average Total LLM Calls per Query**: `{m.get('avg_llm_calls', 0):.2f}`")
    lines.append(f"- **Average Tool Calls per Query**: `{m.get('avg_tool_calls', 0):.2f}`")
    lines.append("")

    # Category Breakdown
    lines.append("## 3. Performance by Target Category")
    lines.append("")
    lines.append("| Category | Total Cases | Sequence Accuracy | Guard Accuracy | Missing Tool Rate | Premature Stop Rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cat in ["tool_necessity", "premature_termination", "multistep_dependency"]:
        cat_cases = [r for r in results if r["category"] == cat and r["status"] == "completed"]
        if cat_cases:
            cat_seq = sum(r["sequence_correct"] for r in cat_cases) / len(cat_cases)
            cat_grd = sum(r["guard_correct"] for r in cat_cases) / len(cat_cases)
            cat_mis = sum(1 for r in cat_cases if r["failure_type"] == "missing_tool") / len(cat_cases)
            cat_prm = sum(1 for r in cat_cases if r["failure_type"] == "premature_stop") / len(cat_cases)
            lines.append(f"| `{cat}` | {len(cat_cases)} | {cat_seq*100:.1f}% | {cat_grd*100:.1f}% | {cat_mis*100:.1f}% | {cat_prm*100:.1f}% |")
    lines.append("")

    # Detailed Per-Case Trace Table
    lines.append("## 4. Per-Case Execution Traces")
    lines.append("")
    lines.append("| Case ID | Category | Expected Sequence | Actual Sequence | Result | Failure Mode | Latency | LLM Calls |")
    lines.append("|---|---|---|---|---|---|---:|---:|")
    for r in results:
        if r["status"] == RATE_LIMIT_SENTINEL:
            lines.append(f"| {r['id']} | {r['category']} | — | — | ⛔ RATE_LIMITED | — | — | — |")
        else:
            exp_str = ", ".join(r["expected_sequence"]) if r["expected_sequence"] else "[]"
            act_str = ", ".join(r["actual_sequence"]) if r["actual_sequence"] else "[]"
            res_icon = "✅ PASS" if r["sequence_correct"] else "❌ FAIL"
            fail_str = r["failure_type"] or "none"
            lines.append(f"| {r['id']} | {r['category']} | `{exp_str}` | `{act_str}` | {res_icon} | {fail_str} | {r['total_latency_s']:.2f}s | {r['total_llm_calls']} |")
    lines.append("")

    # Architectural Summary
    lines.append("## 5. Architectural Improvements Implemented in Phase 3B")
    lines.append("")
    lines.append("1. **Strict Tool Necessity Boundary**:")
    lines.append("   - Explicit prompt requirements that forbid mental arithmetic, forcing `calculator` invocation.")
    lines.append("   - Clear separation between queries answerable strictly from retrieved RAG context vs. queries requiring subsequent arithmetic or external lookup.")
    lines.append("2. **Deterministic Completion Guard (Zero-LLM Overhead)**:")
    lines.append("   - Intercepts premature `action: final` decisions if explicit calculation or search operations from the user query have not been completed.")
    lines.append("   - Re-prompts the planner with specific guard feedback, eliminating premature stops after step 1.")
    lines.append("3. **Repeated Tool Loop Protection**:")
    lines.append("   - Detects consecutive identical `(tool_name, arguments)` dispatches without new information and halts safely (`execution_status='repeated_tool_call'`).")
    lines.append("4. **Exact Latency & Call Instrumentation**:")
    lines.append("   - Traces precise per-step LLM and tool execution durations.")
    lines.append("")

    return "\n".join(lines)


def main():
    dataset_path = args.dataset
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    if args.limit:
        dataset = dataset[: args.limit]

    mode_label = "MOCK LLM" if args.mock else "REAL LLM"
    print(f"=== Phase 3B Reliability Evaluation ({mode_label}) ===")
    print(f"Model   : {'MockLLM' if args.mock else MODEL_NAME}")
    print(f"Cases   : {len(dataset)}")
    print(f"Dataset : {dataset_path}")
    print()

    app = create_runnable_graph()
    results = []
    rate_limited = False

    for i, case in enumerate(dataset):
        if rate_limited:
            results.append({
                "id": case["id"],
                "category": case["category"],
                "query": case["query"],
                "expected_sequence": case["expected_sequence"],
                "status": RATE_LIMIT_SENTINEL,
            })
            continue

        print(f"[{i+1}/{len(dataset)}] [{case['id']}] {case['query'][:65]}...")
        try:
            res = run_case(app, case)
            results.append(res)
            status_icon = "✅" if res["sequence_correct"] else f"❌ ({res['failure_type']})"
            print(f"       → Sequence: {res['actual_sequence']} {status_icon} ({res['total_latency_s']:.2f}s, LLM calls: {res['total_llm_calls']})")
        except Exception as exc:
            if is_rate_limit(exc):
                print(f"  ⛔ RATE LIMIT on {case['id']} — stopping live benchmark.")
                rate_limited = True
                results.append({
                    "id": case["id"],
                    "category": case["category"],
                    "query": case["query"],
                    "expected_sequence": case["expected_sequence"],
                    "status": RATE_LIMIT_SENTINEL,
                })
            else:
                print(f"  ❌ ERROR on {case['id']}: {exc}")
                results.append({
                    "id": case["id"],
                    "category": case["category"],
                    "query": case["query"],
                    "expected_tools": case["expected_tools"],
                    "expected_sequence": case["expected_sequence"],
                    "actual_sequence": [],
                    "final_answer": "",
                    "execution_status": "error",
                    "failure_type": "error",
                    "tool_selection_correct": False,
                    "sequence_correct": False,
                    "multistep_correct": False,
                    "guard_correct": False,
                    "final_before_required_tool": True,
                    "arg_accuracy": 0.0,
                    "tool_success_rate": 0.0,
                    "tool_loop_detected": False,
                    "planner_calls": 0,
                    "total_llm_calls": 0,
                    "total_tool_calls": 0,
                    "planner_llm_time_s": 0.0,
                    "total_latency_s": 0.0,
                    "status": "error",
                    "error": str(exc),
                })
        if not args.mock:
            time.sleep(1.5)

    # Save JSON results
    out_file = RESULTS_DIR / ("phase3b_mock_results.json" if args.mock else "phase3b_live_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw results saved to {out_file}")

    # Generate Report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_text = generate_report(results, is_mock=args.mock, timestamp=timestamp)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Report written to {REPORT_PATH}")

    # Print Summary Metrics
    m = compute_metrics(results)
    if m:
        print("\n── Phase 3B Summary Metrics ──")
        print(f"  Tool Selection Accuracy : {m['tool_selection_acc']*100:.1f}%")
        print(f"  Sequence Accuracy       : {m['sequence_acc']*100:.1f}%")
        print(f"  Multi-Step Completion   : {m['multistep_completion']*100:.1f}%")
        print(f"  Guard Accuracy          : {m['guard_accuracy']*100:.1f}%")
        print(f"  Premature Final Rate    : {m['final_before_required_rate']*100:.1f}%")
        print(f"  Missing Tool Rate       : {m['missing_tool_rate']*100:.1f}%")
        print(f"  Mean Total Latency      : {m['mean_latency_s']:.2f}s")
        print(f"  Avg LLM Calls / Query   : {m['avg_llm_calls']:.1f}")


if __name__ == "__main__":
    main()
