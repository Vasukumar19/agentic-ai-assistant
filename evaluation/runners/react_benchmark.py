"""
Same-model ReAct vs Planner comparison.

Reconstructs the ORIGINAL pre-Planner graph (router -> retrieval ->
context_builder -> agent <-> tools) using the verbatim recovered ReAct
agent_node, and runs it against the same datasets with the same metrics
as evaluate_phase3_live.py. Same model, same tools, same machine.
"""

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from langgraph.graph import StateGraph, END
from langgraph.types import Send
from state import AgentState
from config import MAX_TOOL_STEPS
from nodes import (
    intent_router,
    retrieval_planner_node,
    memory_retriever_node,
    rag_retriever_node,
    context_builder_node,
    tool_node,
)
from evaluation.runners.react_agent_recovered import agent_node
# evaluate_phase3_live parses CLI args at module level; hide ours during import.
_argv = sys.argv
sys.argv = [sys.argv[0]]
from evaluation.metrics.orchestration import (
    evaluate_tool_selection_accuracy,
    evaluate_tool_sequence_accuracy,
)
from evaluate_phase3_live import classify_failure
sys.argv = _argv


def _fan_out(state: dict):
    sends = []
    plan = state.get("retrieval_plan", {})
    if plan.get("profile") or plan.get("semantic"):
        sends.append(Send("memory_retriever", state))
    if plan.get("rag"):
        sends.append(Send("rag_retriever", state))
    if not sends:
        sends.append(Send("context_builder", state))
    return sends


def _route(state: dict):
    route = state.get("route", "research_query")
    if route == "chat":
        return "chat"
    elif route == "memory_update":
        return END  # memory path out of scope for tool benchmarks
    return "retrieval_planner"


def _should_continue(state: dict):
    messages = state.get("messages", [])
    tool_rounds = sum(1 for m in messages if getattr(m, "tool_calls", None))
    if tool_rounds >= MAX_TOOL_STEPS:
        return "end"
    last = messages[-1] if messages else None
    if last is not None and getattr(last, "tool_calls", None):
        return "tools"
    # No explicit answer set yet (agent returned only messages)? treat as end.
    return "end"


def build_react_graph():
    g = StateGraph(AgentState)
    g.add_node("intent_router", intent_router)
    g.add_node("chat", lambda s: {"answer": "(chat out of scope)"})
    g.add_node("retrieval_planner", retrieval_planner_node)
    g.add_node("memory_retriever", memory_retriever_node)
    g.add_node("rag_retriever", rag_retriever_node)
    g.add_node("context_builder", context_builder_node)
    g.add_node("agent", agent_node)
    g.add_node("tools", tool_node)

    g.set_entry_point("intent_router")
    g.add_conditional_edges("intent_router", _route,
                            {"chat": "chat", END: END, "retrieval_planner": "retrieval_planner"})
    g.add_conditional_edges("retrieval_planner", _fan_out,
                            ["memory_retriever", "rag_retriever", "context_builder"])
    g.add_edge("memory_retriever", "context_builder")
    g.add_edge("rag_retriever", "context_builder")
    g.add_edge("context_builder", "agent")
    g.add_conditional_edges("agent", _should_continue, {"tools": "tools", "end": END})
    g.add_edge("tools", "agent")
    return g.compile()


def extract_sequence(state: dict) -> list:
    plan = state.get("retrieval_plan", {})
    actual = []
    if plan.get("rag"):
        actual.append("rag")
    if plan.get("profile") or plan.get("semantic"):
        actual.append("memory_search")
    for m in state.get("messages", []):
        for call in getattr(m, "tool_calls", None) or []:
            actual.append(call["name"])
    return actual


def run_dataset(dataset, app):
    rows = []
    for case in dataset:
        t0 = time.perf_counter()
        try:
            state = app.invoke({"question": case["query"]})
            err = None
        except Exception as exc:
            state, err = {}, str(exc)
        lat = time.perf_counter() - t0

        if err:
            rows.append({"id": case["id"], "status": "error", "error": err[:200],
                         "total_latency_s": round(lat, 2)})
            print(f"  [{case['id']}] ERROR {err[:90]}")
            continue

        actual = extract_sequence(state)
        expected = case["expected_sequence"]
        msgs = state.get("messages", [])
        llm_calls = sum(1 for m in msgs if getattr(m, "type", None) == "ai")
        tool_calls = sum(1 for m in msgs if getattr(m, "tool_calls", None))

        rows.append({
            "id": case["id"],
            "expected": expected,
            "actual": actual,
            "failure": classify_failure(expected, actual),
            "selection_ok": evaluate_tool_selection_accuracy(expected, actual),
            "sequence_ok": evaluate_tool_sequence_accuracy(expected, actual),
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
            "total_latency_s": round(lat, 2),
            "status": "completed",
            "answer_snippet": (state.get("answer") or "")[:120],
        })
        mark = "PASS" if not rows[-1]["failure"] else rows[-1]["failure"]
        print(f"  [{case['id']}] exp={expected} act={actual} {mark} ({lat:.2f}s)")
        time.sleep(0.5)
    return rows


def metrics(rows):
    done = [r for r in rows if r.get("status") == "completed"]
    if not done:
        return {}
    lats = [r["total_latency_s"] for r in done]
    multi = [r for r in done if len(r["expected"]) > 1]
    return {
        "n_completed": len(done),
        "tool_selection_acc": sum(r["selection_ok"] for r in done) / len(done),
        "sequence_acc": sum(r["sequence_ok"] for r in done) / len(done),
        "multistep_completion": (sum(1 for r in multi if r["sequence_ok"]) / len(multi)) if multi else None,
        "missing_tool_rate": sum(1 for r in done if r["failure"] == "missing_tool") / len(done),
        "wrong_tool_rate": sum(1 for r in done if r["failure"] == "wrong_tool") / len(done),
        "premature_stop_rate": sum(1 for r in done if r["failure"] == "premature_stop") / len(done),
        "unnecessary_tool_rate": sum(1 for r in done if r["failure"] == "unnecessary_tool") / len(done),
        "mean_latency_s": statistics.mean(lats),
        "p50_latency_s": statistics.median(lats),
        "p95_latency_s": sorted(lats)[int(len(lats) * 0.95)],
        "avg_llm_calls": statistics.mean(r["llm_calls"] for r in done),
        "avg_tool_calls": statistics.mean(r["tool_calls"] for r in done),
    }


def main():
    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "evaluation/datasets/phase3_live_10.json"
    dataset = json.load(open(dataset_path, encoding="utf-8"))
    print(f"=== ReAct (recovered) + Qwen3 on {dataset_path} ===")
    app = build_react_graph()
    rows = run_dataset(dataset, app)
    m = metrics(rows)
    print("\n── ReAct Metrics ──")
    for k, v in m.items():
        print(f"  {k}: {v*100:.1f}%" if isinstance(v, float) and v <= 1 else f"  {k}: {v}")

    out = Path("evaluation/results/react_qwen3_" + Path(dataset_path).stem + ".json")
    json.dump({"metrics": m, "rows": rows}, open(out, "w", encoding="utf-8"), indent=2)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
