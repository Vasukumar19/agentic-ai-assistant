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
from config import MAX_TOOL_ITERATIONS, CHAT_HISTORY_PATH
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
    agent_node,
    tool_node,
)
import json
import logging

logger = logging.getLogger(__name__)


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

    return {}


def should_continue(state: dict):
    """
    Determine if agent should continue to tool use or return final answer.

    Used in research_query path to loop back to agent after tool execution.
    """
    messages = state.get("messages", [])

    if not messages:
        return "end"

    # Count tool call rounds
    tool_rounds = sum(
        1 for m in messages
        if hasattr(m, 'tool_calls') and m.tool_calls
    )
    if tool_rounds >= MAX_TOOL_ITERATIONS:
        logger.info("Max tool iterations (%d) reached", MAX_TOOL_ITERATIONS)
        return "end"

    last_message = messages[-1]

    # If last message has tool_calls, we need to execute tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"

    # Otherwise, we're done
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
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    # Save history (used by all paths)
    graph.add_node("save_history", save_history_node)

    # ─── EDGES ───────────────────────────────────────────────────────────

    # Start → router
    graph.set_entry_point("intent_router")

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
    graph.add_edge("context_builder", "agent")

    # Agent → tools loop or end
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": "save_history",
        }
    )

    # Tools → back to agent
    graph.add_edge("tools", "agent")

    # All paths end at save_history
    graph.add_edge("save_history", END)

    return graph


def create_runnable_graph():
    """
    Compile the graph into a runnable object.
    """
    graph = build_graph()
    return graph.compile()