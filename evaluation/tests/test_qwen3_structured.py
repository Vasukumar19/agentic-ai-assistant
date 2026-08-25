"""
Real Qwen3 structured-output tests.

These run ONLY when LLM_PROVIDER=ollama and require a reachable Ollama server.
They validate that the EXISTING PlannerDecision schema works unmodified with
Qwen3 via with_structured_output(). A PASS means the model actually produced
a validated PlannerDecision.
"""

import importlib
import os
import time

import pytest
from langchain_core.messages import SystemMessage, HumanMessage

import llm as llm_module


def _ensure_real_llm():
    """If an earlier test module cached MockLLM in sys.modules, reload the
    real provider so this test exercises actual model execution."""
    if type(llm_module.llm).__name__ == "MockLLM":
        importlib.reload(llm_module)
    return llm_module.llm


llm = _ensure_real_llm()

from nodes.planner_node import PlannerDecision, PLANNER_SYSTEM_PROMPT  # noqa: E402

pytestmark = pytest.mark.skipif(
    type(llm).__name__ != "ChatOllama",
    reason="Requires the real Ollama provider (LLM_PROVIDER=ollama)",
)


def _decide(query: str, context: str = "") -> PlannerDecision:
    user_prompt = f"RETRIEVED CONTEXT:\n{context}\n\nUser Query: {query}" if context else f"User Query: {query}"
    sllm = llm.with_structured_output(PlannerDecision)
    return sllm.invoke([
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])


def test_structured_final_response():
    t0 = time.perf_counter()
    d = _decide("What is the capital of France?", context="Paris is the capital of France.")
    latency = time.perf_counter() - t0
    assert isinstance(d, PlannerDecision)
    assert d.action == "final"
    assert d.answer and "Paris" in d.answer
    assert latency < 120


def test_structured_calculator_action():
    d = _decide("What is 128 / 8?")
    assert d.action == "tool"
    assert d.tool == "calculator"
    assert d.arguments is not None and "expression" in d.arguments


def test_structured_web_search_action():
    d = _decide("What is the current population of Japan?")
    assert d.action == "tool"
    assert d.tool == "web_search"
    assert d.arguments is not None and d.arguments.get("query")


def test_structured_multistep_first_action_is_search():
    d = _decide("Find the current population of Japan and calculate what 0.5% of it would be.")
    assert d.action == "tool"
    # First step of a dependent multi-step query must be the lookup, not math.
    assert d.tool == "web_search"
    assert d.arguments is not None and d.arguments.get("query")


def test_no_hallucinated_tool_names():
    for q in ["What is sqrt(144)?", "Who is the CEO of Tesla?", "Summarize the retrieved policy."]:
        d = _decide(q)
        assert d.action in ("tool", "final")
        if d.action == "tool":
            assert d.tool in ("calculator", "web_search"), f"Hallucinated tool: {d.tool}"
