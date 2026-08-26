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

from nodes.planner_node import PlannerDecision, PLANNER_SYSTEM_PROMPT  # noqa: E402

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


def test_gemma_structured_final_response():
    t0 = time.perf_counter()
    d = _decide("What is the capital of France?", context="Paris is the capital of France.")
    latency = time.perf_counter() - t0
    assert isinstance(d, PlannerDecision)
    assert d.action == "final"
    assert d.answer and "Paris" in d.answer
    assert latency < 120


def test_gemma_structured_calculator_action():
    d = _decide("What is 128 / 8?")
    assert d.action == "tool"
    assert d.tool == "calculator"
    assert d.arguments is not None and "expression" in d.arguments


def test_gemma_structured_web_search_action():
    d = _decide("What is the current population of Japan?")
    assert d.action == "tool"
    assert d.tool == "web_search"
    assert d.arguments is not None and d.arguments.get("query")


def test_gemma_structured_multistep_first_action_is_search():
    d = _decide("Find the current population of Japan and calculate what 0.5% of it would be.")
    assert d.action == "tool"
    assert d.tool == "web_search"
    assert d.arguments is not None and d.arguments.get("query")


def test_gemma_no_hallucinated_tool_names():
    for q in ["What is sqrt(144)?", "Who is the CEO of Tesla?", "Summarize the retrieved policy."]:
        d = _decide(q)
        assert d.action in ("tool", "final")
        if d.action == "tool":
            assert d.tool in ("calculator", "web_search"), f"Hallucinated tool: {d.tool}"


def test_gemma_tool_arguments_valid():
    d = _decide("Calculate 25 * 40")
    assert d.action == "tool"
    assert d.tool == "calculator"
    # arguments must be parseable and contain expression
    assert isinstance(d.arguments, dict)
    assert "expression" in d.arguments
    assert isinstance(d.arguments["expression"], str)


def test_gemma_pydantic_validation():
    # PlannerDecision must validate; malformed output should raise, not silently pass
    d = _decide("What is the capital of France?")
    # If we got here without exception, validation passed
    assert d.model_validate(d.model_dump()) is not None
