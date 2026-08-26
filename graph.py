"""
LangGraph State Graph Builder
=============================

Constructs the complete workflow graph with:
- Three main execution paths (chat, memory_update, research_query)
- Conditional routing based on intent
- Tool loop for research_query path
- Save history at all terminal states
"""

from langgraph.graph import StateGraph, END
from langgraph.types import Send
from state import AgentState
from config import MAX_TOOL_STEPS, CHAT_HISTORY_PATH
from nodes import (
    intent_router,
    chat_node,
    memory_extractor_node,
    memory_saver_node,
    memory_response_node,
    retrieval_planner_node,
    memory_retriever_node,
    rag_retriever_node,
    context_builder_node,
    planner_node,
    tool_node,
)
import json
import logging
import time

logger = logging.getLogger(__name__)


def trace_init_node(state: dict) -> dict:
    """Phase 5: ensure request_id/trace_id, emit REQUEST event, init timers."""
    from observability.ids import ensure_trace_ids
    from observability.trace import make_event, append_event

    ensure = ensure_trace_ids(state)
    for k, v in ensure.items():
        if k not in state or state.get(k) is None:
            state[k] = v
    # also ensure required lists
    if state.get("trace_events") is None:
        state["trace_events"] = []
    if state.get("trace_step") is None:
        state["trace_step"] = 0
    if state.get("latency_breakdown") is None:
        state["latency_breakdown"] = {}
    if state.get("tool_failure_counts") is None:
        state["tool_failure_counts"] = {}
    if state.get("llm_usage") is None:
        state["llm_usage"] = []
    if not state.get("trace_start_ms"):
        state["trace_start_ms"] = time.perf_counter() * 1000

    q = state.get("question", "")
    # emit REQUEST as first event (if not already emitted for this trace)
    has_request = any(e.get("event_type") == "REQUEST" for e in (state.get("trace_events") or []))
    if not has_request:
        ev = make_event(state, "REQUEST", "trace_init", status="success",
                        metadata={"question": q[:500], "question_chars": len(q)})
        append_event(state, ev)
    # return trace fields so LangGraph merges them
    return {
        "request_id": state["request_id"],
        "trace_id": state["trace_id"],
        "trace_events": state["trace_events"],
        "trace_step": state["trace_step"],
        "latency_breakdown": state["latency_breakdown"],
        "tool_failure_counts": state["tool_failure_counts"],
        "llm_usage": state["llm_usage"],
        "trace_start_ms": state["trace_start_ms"],
    }


def save_history_node(state: dict) -> dict:
    """
    Save Q&A pair to chat history.

    Args:
        state: AgentState with 'question' and 'answer' fields

    Returns:
        Updated state (or empty dict)
    """
    question = state.get("question", "")
    answer = state.get("answer", "") or "I wasn't able to complete the request after several tool attempts."

    CHAT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing history
    if CHAT_HISTORY_PATH.exists():
        try:
            with open(CHAT_HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"[Save History] JSON parse failed: {e}")
            history = []
    else:
        history = []

    # Add new messages
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})

    # Cap to 100 entries
    history = history[-100:]

    # Save
    with open(CHAT_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)

    logger.info("Saved Q&A pair (%d total entries)", len(history))

    # Phase 5: emit FINAL_ANSWER trace event + persist to JSONL
    try:
        from observability.trace import make_event, append_event, add_latency
        from observability.storage import persist_trace
        from config import MAX_EXECUTION_STEPS
        t_start = state.get("trace_start_ms")
        total_ms = int(time.perf_counter() * 1000 - t_start) if t_start else None
        if total_ms is not None:
            state["total_latency_ms"] = total_ms
        # Phase 8: routers cannot persist state — recompute terminal status here.
        exec_status = state.get("execution_status") or "completed"
        budget = max(MAX_EXECUTION_STEPS, 1)
        if exec_status == "running" and state.get("tool_call_count", 0) >= budget:
            exec_status = "budget_exhausted"
            state["execution_status"] = exec_status
        ev = make_event(state, "FINAL_ANSWER", "save_history",
                        duration_ms=total_ms,
                        status="success" if exec_status not in ("error", "budget_exhausted") else "error",
                        metadata={
                            "answer_chars": len(answer),
                            "answer_preview": answer[:400],
                            "planner_steps": state.get("tool_call_count", 0),
                            "tool_calls": len(state.get("tool_results") or []),
                            "execution_status": exec_status,
                            "termination_reason": ("budget_exhausted" if exec_status == "budget_exhausted"
                                                   else state.get("tool_loop_detected") and "loop_detected" or None),
                            "execution_step": state.get("tool_call_count", 0),
                            "execution_budget": budget,
                            "remaining_budget": max(0, budget - state.get("tool_call_count", 0)),
                            "route": state.get("route", ""),
                            "total_latency_ms": total_ms,
                            "latency_breakdown": state.get("latency_breakdown", {}),
                        })
        append_event(state, ev)
        # persist all events for this trace
        persist_trace(state)
    except Exception as e:
        logger.warning(f"[Trace] persist failed: {e}")

    return {
        "trace_events": state.get("trace_events"),
        "trace_step": state.get("trace_step"),
        "total_latency_ms": state.get("total_latency_ms"),
    }


def should_continue(state: dict):
    """
    Determine if agent should continue to tool use or return final answer.
    Phase 8: MAX_EXECUTION_STEPS is the legitimate-workflow budget;
    loop/repetition protection lives in planner_node + per-tool failure counts.
    """
    from config import MAX_TOOL_FAILURES_PER_TOOL, MAX_EXECUTION_STEPS
    budget = max(MAX_EXECUTION_STEPS, 1)
    if state.get("tool_call_count", 0) >= budget:
        logger.info("Execution budget (%d) reached", budget)
        try:
            from observability.trace import make_event, append_event
            from observability.errors import make_error_payload, ErrorType
            err = make_error_payload(ErrorType.TOOL_EXECUTION_ERROR.value, "planner",
                                     f"execution budget ({budget}) exhausted",
                                     retryable=False, trace_id=state.get("trace_id"))
            ev = make_event(state, "ERROR", "planner", status="error",
                            metadata={"termination_reason": "budget_exhausted",
                                      "execution_step": state.get("tool_call_count", 0),
                                      "execution_budget": budget,
                                      "remaining_budget": 0,
                                      "loop_detected": bool(state.get("tool_loop_detected")),
                                      "circuit_breaker": "execution_budget"},
                            error=err)
            append_event(state, ev)
        except Exception:
            pass
        # explicit terminal status so FINAL_ANSWER distinguishes completion vs budget stop
        state["execution_status"] = "budget_exhausted"
        return "end"

    # per-tool failure circuit breaker
    counts = state.get("tool_failure_counts") or {}
    for tool, cnt in counts.items():
        if cnt >= MAX_TOOL_FAILURES_PER_TOOL:
            logger.info("Per-tool failure limit reached for %s (%d)", tool, cnt)
            try:
                from observability.trace import make_event, append_event
                from observability.errors import make_error_payload, ErrorType
                err = make_error_payload(ErrorType.TOOL_EXECUTION_ERROR.value, "tools",
                                         f"per-tool failure limit ({MAX_TOOL_FAILURES_PER_TOOL}) for {tool}",
                                         retryable=False, trace_id=state.get("trace_id"))
                ev = make_event(state, "ERROR", "tools", status="error",
                                metadata={"circuit_breaker": "per_tool", "tool": tool,
                                          "failures": cnt,
                                          "execution_step": state.get("tool_call_count", 0),
                                          "execution_budget": budget,
                                          "remaining_budget": max(0, budget - state.get("tool_call_count", 0)),
                                          "loop_detected": True,
                                          "termination_reason": "loop_detected_per_tool_failures"},
                                error=err)
                append_event(state, ev)
            except Exception:
                pass
            return "end"

    status = state.get("execution_status")
    if status == "running":
        return "tools"
    
    return "end"


def fan_out_retrievers(state: dict):
    """
    Fan out to multiple retrieval nodes in parallel based on the retrieval plan.
    """
    sends = []
    plan = state.get("retrieval_plan", {})
    if plan.get("profile") or plan.get("semantic"):
        sends.append(Send("memory_retriever", state))
    if plan.get("rag"):
        sends.append(Send("rag_retriever", state))
    if not sends:
        sends.append(Send("context_builder", state))
    return sends


def route_from_router(state: dict):
    """Directs flow from the router to the appropriate next node."""
    route = state.get("route", "research_query")
    if route == "chat":
        return "chat"
    elif route == "memory_update":
        return "memory_extractor"
    return "retrieval_planner"


def build_graph() -> StateGraph:
    """
    Build the complete LangGraph workflow.

    Structure:

    START
      ↓
    intent_router
      ├→ CHAT path
      ├→ MEMORY_UPDATE path
      └→ RESEARCH_QUERY path

    Each path converges on save_history before END.
    """

    # Create graph
    graph = StateGraph(AgentState)

    # ─── NODES ───────────────────────────────────────────────────────────

    graph.add_node("trace_init", trace_init_node)
    graph.add_node("intent_router", intent_router)

    # Chat path
    graph.add_node("chat", chat_node)

    # Memory update path
    graph.add_node("memory_extractor", memory_extractor_node)
    graph.add_node("memory_saver", memory_saver_node)
    graph.add_node("memory_response", memory_response_node)

    # Research query path
    graph.add_node("retrieval_planner", retrieval_planner_node)
    graph.add_node("memory_retriever", memory_retriever_node)
    graph.add_node("rag_retriever", rag_retriever_node)
    graph.add_node("context_builder", context_builder_node)
    graph.add_node("planner", planner_node)
    graph.add_node("tools", tool_node)

    # Save history (used by all paths)
    graph.add_node("save_history", save_history_node)

    # ─── EDGES ───────────────────────────────────────────────────────────

    # Start → trace_init → router
    graph.set_entry_point("trace_init")
    graph.add_edge("trace_init", "intent_router")

    # Router branches
    graph.add_conditional_edges(
        "intent_router",
        route_from_router,
        ["chat", "memory_extractor", "retrieval_planner"]
    )

    # Chat path
    graph.add_edge("chat", "save_history")

    # Memory update path
    graph.add_edge("memory_extractor", "memory_saver")
    graph.add_edge("memory_saver", "memory_response")
    graph.add_edge("memory_response", "save_history")

    # Research query path
    graph.add_conditional_edges(
        "retrieval_planner",
        fan_out_retrievers,
        ["memory_retriever", "rag_retriever", "context_builder"]
    )
    graph.add_edge("memory_retriever", "context_builder")
    graph.add_edge("rag_retriever", "context_builder")
    graph.add_edge("context_builder", "planner")

    # Planner -> tools loop or end
    graph.add_conditional_edges(
        "planner",
        should_continue,
        {
            "tools": "tools",
            "end": "save_history",
        }
    )

    # Tools -> back to planner
    graph.add_edge("tools", "planner")

    # All paths end at save_history
    graph.add_edge("save_history", END)

    return graph


def create_runnable_graph():
    """
    Compile the graph into a runnable object.
    """
    graph = build_graph()
    return graph.compile()