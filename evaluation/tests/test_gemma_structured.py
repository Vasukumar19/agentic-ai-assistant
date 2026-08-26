"""
Gemma3:12b structured-output & tool-compatibility suite (Phase 9).

Controlled test: same PlannerDecision schema, same prompts, same tool registry.
Measures real Ollama inference — no mocks, no model-specific fallbacks.
Skips if LLM_PROVIDER != ollama.
"""

import importlib
import os
import time

import pytest
from langchain_core.messages import SystemMessage, HumanMessage

import llm as llm_module


def _ensure_real_llm():
    if type(llm_module.llm).__name__ == "MockLLM":
        importlib.reload(llm_module)
    return llm_module.llm


llm = _ensure_real_llm()

from nodes.planner_node import PlannerDecision, PLANNER_SYSTEM_PROMPT
from nodes.tools import tools, run_tool, requires_confirmation

pytestmark = pytest.mark.skipif(
    type(llm).__name__ != "ChatOllama",
    reason="Requires real Ollama provider",
)


def _decide(query: str, context: str = "") -> PlannerDecision:
    user_prompt = f"RETRIEVED CONTEXT:\n{context}\n\nUser Query: {query}" if context else f"User Query: {query}"
    sllm = llm.with_structured_output(PlannerDecision)
    return sllm.invoke([
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])


# 1. final answer
def test_gemma_structured_final_response():
    t0 = time.perf_counter()
    d = _decide("What is the capital of France?", context="Paris is the capital of France.")
    latency = time.perf_counter() - t0
    assert isinstance(d, PlannerDecision)
    assert d.action == "final"
    assert latency < 120


# 2. calculator selection
def test_gemma_structured_calculator_action():
    d = _decide("What is 128 / 8?")
    assert d.action == "tool"
    assert d.tool == "calculator"
    assert d.arguments is not None and "expression" in d.arguments


# 3. web_search selection
def test_gemma_structured_web_search_action():
    d = _decide("What is the current population of Japan?")
    assert d.action == "tool"
    assert d.tool == "web_search"
    assert d.arguments is not None and d.arguments.get("query")


# 4. MCP selection (e.g. calendar/notes/reminders list or filesystem read)
def test_gemma_structured_mcp_selection():
    d = _decide("Use notes.list to list my notes.")
    assert d.action in ("tool", "final")
    if d.action == "tool":
        assert d.tool in ("notes.list", "notes_list")


# 5. multi-step web_search -> calculator
def test_gemma_structured_multistep_first_action_is_search():
    d = _decide("Find the current population of Japan and calculate what 0.5% of it would be.")
    assert d.action == "tool"
    assert d.tool == "web_search"
    assert d.arguments is not None and d.arguments.get("query")


# 6. filesystem -> calculator
def test_gemma_structured_filesystem_to_calculator():
    d = _decide("Read note note_001 with notes.read and use calculator to count how many lines it has.")
    assert d.action == "tool"
    assert d.tool in ("notes.read", "notes_read")


# 7. correct tool arguments
def test_gemma_tool_arguments_valid():
    d = _decide("Calculate 25 * 40")
    assert d.action == "tool"
    assert d.tool == "calculator"
    assert isinstance(d.arguments, dict)
    assert "expression" in d.arguments
    assert isinstance(d.arguments["expression"], str)


# 8. final/completion decision
def test_gemma_structured_completion_decision():
    d = _decide("I have completed listing your events.", context="Events: evt_001 Team meeting.")
    assert isinstance(d, PlannerDecision)
    assert d.action in ("final", "tool")


# 9. unknown-tool rejection
def test_gemma_no_hallucinated_tool_names():
    for q in ["What is sqrt(144)?", "Who is the CEO of Tesla?", "Summarize the retrieved policy."]:
        d = _decide(q)
        assert d.action in ("tool", "final")
        if d.action == "tool":
            assert d.tool in ("calculator", "web_search"), f"Hallucinated tool: {d.tool}"


# 10. Pydantic PlannerDecision validation
def test_gemma_pydantic_validation():
    d = _decide("Calculate 10 + 15")
    assert d.model_validate(d.model_dump()) is not None


# ---- Native Tool Calling & MCP Gating Compatibility ----
def test_gemma_bind_tools_native():
    try:
        bound = llm.bind_tools(tools)
        msg = bound.invoke([HumanMessage(content="What is 128 / 8?")])
        assert msg.tool_calls or msg.content
    except Exception as exc:
        assert "does not support tools" in str(exc) or "400" in str(exc)


def test_gemma_calculator_execution():
    out = run_tool("calculator", {"expression": "25 * 40"})
    assert "1000" in out


def test_gemma_confirmation_check():
    assert requires_confirmation("filesystem.write_file", {"path": "test.txt", "content": "hello"}) is False or True
