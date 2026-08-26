"""
Gemma3:12b local smoke tests through the FULL LangGraph agent.

Runs the 6 canonical tool-orchestration scenarios end-to-end and records:
expected vs actual tool sequences, tool args/results, LLM call counts,
latency, execution status. Saves JSON to evaluation/results/gemma3_smoke.json.
"""

import json
import os
import sys
import time
from pathlib import Path

# Ensure Ollama & Gemma settings
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["LLM_MODEL"] = "gemma3:12b"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_REASONING"] = "0"
os.environ["MAX_EXECUTION_STEPS"] = "10"

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from graph import create_runnable_graph
from evaluate_phase3_live import extract_planner_trace, classify_failure

SMOKE_CASES = [
    {
        "id": "smoke_1",
        "name": "Calculator",
        "query": "What is 128 / 8?",
        "expected_sequence": ["calculator"],
    },
    {
        "id": "smoke_2",
        "name": "Web Search",
        "query": "What is the current population of Japan?",
        "expected_sequence": ["web_search"],
    },
    {
        "id": "smoke_3",
        "name": "Search + Calculator",
        "query": "Find the current population of Japan and calculate 0.5% of it.",
        "expected_sequence": ["web_search", "calculator"],
    },
    {
        "id": "smoke_4",
        "name": "RAG + Calculator",
        "query": "According to the document, what is the hardware stipend and calculate the amount for 3 employees.",
        "expected_sequence": ["rag", "calculator"],
    },
    {
        "id": "smoke_5",
        "name": "RAG only",
        "query": "According to our company policy, what is our remote work policy?",
        "expected_sequence": ["rag"],
    },
    {
        "id": "smoke_6",
        "name": "Direct answer",
        "query": "What does 'retrieval augmented generation' mean?",
        "expected_sequence": [],
    },
]


def run_smoke():
    app = create_runnable_graph()
    results = []
    for case in SMOKE_CASES:
        print(f"\n=== {case['id']}: {case['name']} ===")
        print(f"Query: {case['query']}")
        t0 = time.perf_counter()
        try:
            final_state = app.invoke({"question": case["query"]})
            error = None
        except Exception as exc:
            final_state = {}
            error = str(exc)
        latency = time.perf_counter() - t0

        if error:
            results.append({**case, "execution_status": "error", "failure_reason": error,
                            "latency_s": round(latency, 2), "result": "ERROR"})
            print(f"  ERROR: {error}")
            continue

        trace = extract_planner_trace(final_state)
        actual = trace["actual_sequence"]
        failure = classify_failure(case["expected_sequence"], actual)
        status = final_state.get("execution_status", "?")

        exec_trace = final_state.get("execution_trace", [])
        planner_calls = sum(1 for tr in exec_trace if str(tr.get("step", "")).startswith("planner"))

        rec = {
            **case,
            "actual_sequence": actual,
            "tool_results": trace["arg_trace"],
            "final_answer": (trace.get("final_answer") or "")[:400],
            "planner_calls_actual": planner_calls,
            "llm_calls": trace["llm_calls"],
            "tool_call_count": trace["tool_call_count"],
            "execution_status": status,
            "failure_reason": failure,
            "latency_s": round(latency, 2),
            "result": "PASS" if failure is None else "FAIL",
        }
        results.append(rec)
        print(f"  Expected : {case['expected_sequence']}")
        print(f"  Actual   : {actual}")
        for tr in trace["arg_trace"]:
            out_preview = str(tr['output'])[:100] if tr['output'] else ""
            print(f"    - {tr['tool']}({tr['args']}) -> {out_preview}")
        print(f"  Status   : {status} | planner_calls={planner_calls} | "
              f"llm_calls={trace['llm_calls']} | latency={latency:.2f}s")
        print(f"  Answer   : {(trace.get('final_answer') or '')[:150]}")
        print(f"  RESULT   : {rec['result']}")

    out = Path("evaluation/results/gemma3_smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")

    n_pass = sum(1 for r in results if r["result"] == "PASS")
    print(f"\n=== GEMMA SMOKE SUMMARY: {n_pass}/{len(results)} PASS ===")
    return results


if __name__ == "__main__":
    run_smoke()
