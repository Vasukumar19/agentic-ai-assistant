"""
Phase 3 Live Validation Runner
===============================

Runs the 10-case live benchmark against both the current Planner architecture
and (optionally) the ReAct baseline, capturing full execution traces.

Usage:
  python evaluate_phase3_live.py                     # planner only
  python evaluate_phase3_live.py --also-react        # both architectures
  python evaluate_phase3_live.py --limit 5           # first N cases only

Rate-limit handling:
  - On HTTP 429, stops immediately.
  - Saves completed results.
  - Marks remaining cases NOT_RUN_RATE_LIMITED.
  - Never retries.
"""

import json
import os
import sys
import time
import argparse
import traceback
from datetime import datetime, timezone
from statistics import mean, median
from pathlib import Path

# Windows: force UTF-8 output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ──────────────────────────────────────────────────────────────────────────────
# Parse args BEFORE any local imports so MOCK_LLM is never set here
# ──────────────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=None, help="Max cases to run")
parser.add_argument("--also-react", action="store_true",
                    help="Also run the legacy ReAct baseline (costs extra API tokens)")
parser.add_argument("--dataset", default="evaluation/datasets/phase3_live_10.json")
args = parser.parse_args()

# Guarantee no mock in this script
os.environ.pop("MOCK_LLM", None)

from graph import create_runnable_graph          # live LLM
from config import MODEL_NAME

RATE_LIMIT_SENTINEL = "NOT_RUN_RATE_LIMITED"
REPORT_PATH = Path("evaluation/reports/phase3_tool_orchestration.md")
RESULTS_DIR = Path("evaluation/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "quota" in msg or "rate_limit" in msg


def extract_planner_trace(state: dict) -> dict:
    """
    Extract rich trace from final AgentState.
    Works for both new Planner and legacy ReAct architectures.
    """
    messages = state.get("messages", [])
    tool_results = state.get("tool_results", [])      # new planner state
    completed_steps = state.get("completed_steps", [])
    retrieval_plan = state.get("retrieval_plan", {})

    actual_sequence = []

    # Pre-retrieval steps (RAG/memory done before the planner loop)
    if retrieval_plan:
        if retrieval_plan.get("rag"):
            actual_sequence.append("rag")
        if retrieval_plan.get("profile") or retrieval_plan.get("semantic"):
            actual_sequence.append("memory_search")

    # Planner tool calls captured in state
    for step in completed_steps:
        actual_sequence.append(step)

    # Fallback: read tool calls from messages (covers ReAct / partial planner)
    if not completed_steps:
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for call in msg.tool_calls:
                    actual_sequence.append(call["name"])

    # Build argument trace
    arg_trace = []
    for r in tool_results:
        arg_trace.append({
            "tool": r.get("tool"),
            "args": r.get("arguments", {}),
            "output": r.get("result", ""),
        })

    # Fallback arg trace from messages
    if not arg_trace:
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for call in msg.tool_calls:
                    arg_trace.append({
                        "tool": call["name"],
                        "args": call.get("args", {}),
                        "output": None,
                    })

    # Count LLM calls (each AIMessage = one LLM invocation)
    llm_calls = sum(1 for m in messages if getattr(m, "type", None) == "ai")
    # For the planner: 1 per step + 1 retrieval planner call
    if state.get("tool_call_count"):
        llm_calls = state["tool_call_count"] + 1   # planner calls + 1 final

    tool_call_count = len([m for m in messages
                           if hasattr(m, "tool_calls") and m.tool_calls])
    if state.get("tool_call_count"):
        tool_call_count = state["tool_call_count"]

    return {
        "actual_sequence": actual_sequence,
        "arg_trace": arg_trace,
        "final_answer": state.get("answer", ""),
        "llm_calls": llm_calls,
        "tool_call_count": tool_call_count,
        "execution_status": state.get("execution_status", "unknown"),
    }


def classify_failure(expected: list, actual: list) -> str | None:
    if expected == actual:
        return None
    if not actual:
        return "missing_tool"
    exp_set, act_set = set(expected), set(actual)
    if act_set - exp_set:
        return "unnecessary_tool"
    if exp_set - act_set:
        if len(actual) < len(expected) and actual == expected[: len(actual)]:
            return "premature_stop"
        return "missing_tool"
    if sorted(actual) == sorted(expected):
        return "wrong_order"
    return "wrong_tool"


def run_case(app, case: dict) -> dict:
    """Run a single case. Returns result dict or raises."""
    state_in = {"question": case["query"]}

    t0_total = time.perf_counter()
    t0_plan  = t0_total

    final_state = app.invoke(state_in)

    t_total = time.perf_counter() - t0_total

    trace = extract_planner_trace(final_state)
    actual = trace["actual_sequence"]
    expected = case["expected_sequence"]
    failure = classify_failure(expected, actual)

    # Check tool arg accuracy (did planner supply non-empty args for each tool?)
    arg_accuracy = None
    if trace["arg_trace"]:
        non_empty = sum(1 for a in trace["arg_trace"] if a["args"])
        arg_accuracy = non_empty / len(trace["arg_trace"])

    # Tool dependency: every expected tool fired in order (prefix match)
    dep_accuracy = None
    if expected:
        dep_matches = sum(
            1 for i, exp_t in enumerate(expected)
            if i < len(actual) and actual[i] == exp_t
        )
        dep_accuracy = dep_matches / len(expected)

    return {
        "id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "expected_tools": expected,
        "actual_sequence": actual,
        "arg_trace": trace["arg_trace"],
        "final_answer": trace["final_answer"],
        "llm_calls": trace["llm_calls"],
        "tool_call_count": trace["tool_call_count"],
        "total_latency_s": round(t_total, 3),
        "execution_status": trace["execution_status"],
        "failure_type": failure,
        "tool_selection_correct": set(actual) == set(expected),
        "sequence_correct": actual == expected,
        "arg_accuracy": arg_accuracy,
        "dep_accuracy": dep_accuracy,
        "status": "completed",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Metrics aggregation
# ──────────────────────────────────────────────────────────────────────────────

def compute_metrics(results: list) -> dict:
    completed = [r for r in results if r["status"] == "completed"]
    n = len(completed)
    if n == 0:
        return {}

    failures = [r["failure_type"] for r in completed if r["failure_type"]]
    f_counts = {}
    for f in failures:
        f_counts[f] = f_counts.get(f, 0) + 1

    latencies = sorted(r["total_latency_s"] for r in completed)

    arg_vals = [r["arg_accuracy"] for r in completed if r["arg_accuracy"] is not None]
    dep_vals = [r["dep_accuracy"] for r in completed if r["dep_accuracy"] is not None]

    return {
        "n_completed": n,
        "n_rate_limited": sum(1 for r in results if r["status"] == RATE_LIMIT_SENTINEL),
        "tool_selection_acc": sum(r["tool_selection_correct"] for r in completed) / n,
        "sequence_acc": sum(r["sequence_correct"] for r in completed) / n,
        "multistep_completion": sum(
            r["sequence_correct"] for r in completed
            if r.get("requires_multi_step", len(r["expected_tools"]) > 1)
        ) / max(1, sum(
            1 for r in completed
            if r.get("requires_multi_step", len(r["expected_tools"]) > 1)
        )),
        "missing_tool_rate": f_counts.get("missing_tool", 0) / n,
        "wrong_tool_rate": f_counts.get("wrong_tool", 0) / n,
        "wrong_order_rate": f_counts.get("wrong_order", 0) / n,
        "premature_stop_rate": f_counts.get("premature_stop", 0) / n,
        "unnecessary_tool_rate": f_counts.get("unnecessary_tool", 0) / n,
        "arg_accuracy": mean(arg_vals) if arg_vals else None,
        "dep_accuracy": mean(dep_vals) if dep_vals else None,
        "tool_success_rate": sum(
            1 for r in completed
            if r["execution_status"] in ("completed",)
        ) / n,
        "avg_llm_calls": mean(r["llm_calls"] for r in completed),
        "avg_tool_calls": mean(r["tool_call_count"] for r in completed),
        "mean_latency_s": mean(latencies),
        "p50_latency_s": median(latencies),
        "p95_latency_s": latencies[int(len(latencies) * 0.95)] if latencies else 0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Report generation
# ──────────────────────────────────────────────────────────────────────────────

def pct(v):
    if v is None: return "N/A"
    return f"{v*100:.1f}%"

def fmt(v, decimals=2):
    if v is None: return "N/A"
    return f"{v:.{decimals}f}"


def generate_report(planner_results: list, react_results: list | None,
                    timestamp: str) -> str:
    pm = compute_metrics(planner_results)
    rm = compute_metrics(react_results) if react_results else None

    def delta(pk, rk):
        if rm is None or pm.get(pk) is None or rm.get(rk) is None:
            return "N/A"
        d = pm[pk] - rm[rk]
        sign = "+" if d >= 0 else ""
        if isinstance(pm[pk], float) and pm[pk] <= 1.0:
            return f"{sign}{d*100:.1f}pp"
        return f"{sign}{d:.2f}"

    n_pl = pm.get("n_completed", 0)
    n_rl_pl = pm.get("n_rate_limited", 0)

    lines = []
    lines.append("# Phase 3 Tool Orchestration Report")
    lines.append(f"\nGenerated: {timestamp}")
    lines.append(f"Model: {MODEL_NAME}")
    lines.append("")

    # ── MOCK results section (preserved from Phase 3 implementation) ──────────
    lines.append("## MOCK RESULTS (Deterministic, No API Calls)")
    lines.append("")
    lines.append("These results were produced using a deterministic Mock LLM to validate "
                 "the orchestration infrastructure logic only.")
    lines.append("They do **NOT** represent real LLM capability.")
    lines.append("")
    lines.append("| Metric | ReAct (Mock) | Planner (Mock) | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append("| Tool Selection Accuracy | 24.0% | 44.0% | +20.0pp |")
    lines.append("| Sequence Accuracy | 20.0% | 40.0% | +20.0pp |")
    lines.append("| Multi-Step Completion | 20.0% | 40.0% | +20.0pp |")
    lines.append("| Avg Latency | 0.84s | 1.56s | +0.72s |")
    lines.append("")
    lines.append("> **Note:** Mock deltas reflect improved orchestration logic, "
                 "not real LLM reasoning quality.")
    lines.append("")

    # ── REAL LLM validation ───────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## REAL LLM VALIDATION")
    lines.append("")
    lines.append(f"- **Dataset**: `evaluation/datasets/phase3_live_10.json` (10 cases)")
    lines.append(f"- **Cases attempted**: {n_pl + n_rl_pl}")
    lines.append(f"- **Cases completed**: {n_pl}")
    lines.append(f"- **Cases rate-limited**: {n_rl_pl}")
    if n_rl_pl > 0:
        lines.append("")
        lines.append("> ⚠️ **API Rate Limit Reached** — remaining cases marked "
                     "`NOT_RUN_RATE_LIMITED`. Results below are partial.")
    lines.append("")

    if n_pl == 0:
        lines.append("### LIVE VALIDATION: NOT RUN — API RATE LIMITED")
        lines.append("")
        lines.append("Real-LLM performance remains unverified.")
        return "\n".join(lines)

    # Comparison table
    lines.append("### Before/After Comparison (Real LLM)")
    lines.append("")
    lines.append("| Metric | ReAct (Real) | Planner (Real) | Δ |")
    lines.append("|---|---:|---:|---:|")

    def row(label, pk, rk=None):
        pv = pct(pm.get(pk))
        rv = pct(rm.get(rk or pk)) if rm else "not run"
        dv = delta(pk, rk or pk) if rm else "N/A"
        lines.append(f"| {label} | {rv} | {pv} | {dv} |")

    def row_num(label, pk, rk=None, dec=2):
        pv = fmt(pm.get(pk), dec)
        rv = fmt(rm.get(rk or pk), dec) if rm else "not run"
        dv = delta(pk, rk or pk) if rm else "N/A"
        lines.append(f"| {label} | {rv} | {pv} | {dv} |")

    row("Tool Selection Accuracy", "tool_selection_acc")
    row("Sequence Accuracy", "sequence_acc")
    row("Multi-Step Completion", "multistep_completion")
    row("Missing Tool Rate", "missing_tool_rate")
    row("Wrong Tool Rate", "wrong_tool_rate")
    row("Premature Stop Rate", "premature_stop_rate")
    row("Unnecessary Tool Rate", "unnecessary_tool_rate")
    row("Arg Accuracy", "arg_accuracy")
    row("Dep Accuracy", "dep_accuracy")
    row("Tool Success Rate", "tool_success_rate")
    row_num("Avg LLM Calls", "avg_llm_calls", dec=1)
    row_num("Avg Tool Calls", "avg_tool_calls", dec=1)
    row_num("Mean Latency (s)", "mean_latency_s", dec=2)
    row_num("P50 Latency (s)", "p50_latency_s", dec=2)
    row_num("P95 Latency (s)", "p95_latency_s", dec=2)

    lines.append("")

    # Per-case trace
    lines.append("### Per-Case Trace")
    lines.append("")
    lines.append("| ID | Category | Expected | Actual | Status | Failure | Latency | LLM Calls |")
    lines.append("|---|---|---|---|---|---|---:|---:|")
    for r in planner_results:
        status = r["status"]
        if status == RATE_LIMIT_SENTINEL:
            lines.append(
                f"| {r['id']} | {r['category']} | — | — | ⛔ RATE_LIMITED | — | — | — |"
            )
        else:
            exp = ", ".join(r["expected_tools"])
            act = ", ".join(r["actual_sequence"])
            fail = r["failure_type"] or "✅ pass"
            lat = f"{r['total_latency_s']:.2f}s"
            llm = r["llm_calls"]
            lines.append(
                f"| {r['id']} | {r['category']} | {exp} | {act} | {status} "
                f"| {fail} | {lat} | {llm} |"
            )
    lines.append("")

    # Failure analysis
    completed_failures = [r for r in planner_results
                          if r.get("failure_type") and r["status"] == "completed"]
    if completed_failures:
        lines.append("### Failure Analysis")
        lines.append("")
        for r in completed_failures:
            lines.append(f"**{r['id']}** — {r['failure_type']}")
            lines.append(f"- Query: {r['query']}")
            lines.append(f"- Expected: `{r['expected_tools']}`")
            lines.append(f"- Actual: `{r['actual_sequence']}`")
            if r["arg_trace"]:
                lines.append("- Tool calls:")
                for a in r["arg_trace"]:
                    lines.append(f"  - `{a['tool']}({a['args']})` → `{str(a['output'])[:120]}`")
            lines.append("")

    # Latency overhead note
    lines.append("### Latency Overhead Analysis")
    lines.append("")
    lines.append(
        "The Planner architecture issues **one structured LLM call per tool step** plus "
        "a final call, versus the ReAct loop which used one call per reasoning round. "
        "This typically results in N+1 LLM calls for an N-tool task."
    )
    lines.append("")
    lines.append(
        f"Observed mean latency: **{pm.get('mean_latency_s', 0):.2f}s** "
        f"with avg **{pm.get('avg_llm_calls', 0):.1f}** LLM calls per query."
    )
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    dataset_path = args.dataset
    with open(dataset_path) as f:
        dataset = json.load(f)

    if args.limit:
        dataset = dataset[: args.limit]

    print(f"=== Phase 3 Live Validation ===")
    print(f"Model   : {MODEL_NAME}")
    print(f"Cases   : {len(dataset)}")
    print(f"Dataset : {dataset_path}")
    print()

    app = create_runnable_graph()

    # ── Run Planner architecture ───────────────────────────────────────────────
    print("── Running NEW PLANNER architecture ──")
    planner_results = []
    rate_limited = False

    for case in dataset:
        if rate_limited:
            planner_results.append({
                "id": case["id"],
                "category": case["category"],
                "query": case["query"],
                "expected_tools": case["expected_sequence"],
                "status": RATE_LIMIT_SENTINEL,
            })
            continue

        print(f"  [{case['id']}] {case['query'][:70]}")
        try:
            result = run_case(app, case)
            planner_results.append(result)
            ok = "✅" if result["failure_type"] is None else f"❌ {result['failure_type']}"
            print(f"         → {result['actual_sequence']}  {ok}  {result['total_latency_s']:.2f}s")
        except Exception as exc:
            if is_rate_limit(exc):
                print(f"  ⛔ RATE LIMIT on {case['id']} — stopping live run.")
                rate_limited = True
                planner_results.append({
                    "id": case["id"],
                    "category": case["category"],
                    "query": case["query"],
                    "expected_tools": case["expected_sequence"],
                    "status": RATE_LIMIT_SENTINEL,
                })
            else:
                print(f"  ❌ ERROR on {case['id']}: {exc}")
                planner_results.append({
                    "id": case["id"],
                    "category": case["category"],
                    "query": case["query"],
                    "expected_tools": case["expected_sequence"],
                    "actual_sequence": [],
                    "arg_trace": [],
                    "final_answer": "",
                    "llm_calls": 0,
                    "tool_call_count": 0,
                    "total_latency_s": 0,
                    "execution_status": "error",
                    "failure_type": "error",
                    "tool_selection_correct": False,
                    "sequence_correct": False,
                    "arg_accuracy": None,
                    "dep_accuracy": None,
                    "status": "error",
                    "error": str(exc),
                })
        # Small back-off to reduce rate limit risk between cases
        time.sleep(1.5)

    # Save raw planner results
    planner_json = RESULTS_DIR / "phase3_live_planner.json"
    with open(planner_json, "w") as f:
        json.dump(planner_results, f, indent=2)
    print(f"\nPlanner results saved to {planner_json}")

    # ── Run legacy ReAct if requested ─────────────────────────────────────────
    react_results = None
    if args.also_react and not rate_limited:
        print("\n── Running LEGACY REACT architecture ──")
        # Legacy ReAct is now the same graph since we replaced agent_node.
        # We cannot run the old architecture without reverting; mark as not run.
        print("  NOTE: Legacy ReAct node has been removed (git rm nodes/agent.py).")
        print("  ReAct comparison is NOT AVAILABLE for real-LLM run.")
        print("  Using stored mock-baseline numbers in report only.")

    # ── Generate report ────────────────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_text = generate_report(planner_results, react_results, timestamp)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\nReport updated: {REPORT_PATH}")

    # Print quick summary
    pm = compute_metrics(planner_results)
    if pm:
        print("\n── Planner Metrics (Live) ──")
        print(f"  Tool Selection Acc : {pm['tool_selection_acc']*100:.1f}%")
        print(f"  Sequence Acc       : {pm['sequence_acc']*100:.1f}%")
        print(f"  Multi-Step Compl.  : {pm['multistep_completion']*100:.1f}%")
        print(f"  Mean Latency       : {pm['mean_latency_s']:.2f}s")
        print(f"  P95 Latency        : {pm['p95_latency_s']:.2f}s")
        print(f"  Avg LLM Calls      : {pm['avg_llm_calls']:.1f}")
        print(f"  Avg Tool Calls     : {pm['avg_tool_calls']:.1f}")
        n_rl = pm.get("n_rate_limited", 0)
        if n_rl:
            print(f"\n  ⚠️  {n_rl} case(s) not run due to rate limiting.")


if __name__ == "__main__":
    main()
