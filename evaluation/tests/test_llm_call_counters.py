"""
Instrumentation counter tests (Phase 10).

Verifies that planner_calls / tool_calls / total_llm_calls are derived from
ACTUAL graph execution (execution_trace + state), not from expected sequences.

Uses MockLLM (MOCK_LLM=1) for determinism; the counters themselves live in
planner_node.execution_trace, so this validates instrumentation logic only.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Isolation fix (Phase 8 regression finding): this module previously set
# MOCK_LLM=1 at import time, which built llm.py's MockLLM singleton and cached
# it in sys.modules for the whole pytest session — poisoning every later LLM
# test with canned answers ("task complete."). We now patch each consumer
# module's `llm` reference for the duration of this module only, then restore.
import llm as _llm_mod  # noqa: E402
from evaluation.mock_llm import MockLLM  # noqa: E402
from importlib import import_module  # noqa: E402
# nodes.planner_node is shadowed by a function attr on the package; use importlib
_CONSUMER_MODS = ["nodes.planner_node", "nodes.router", "nodes.chat",
                  "nodes.rag_retriever", "nodes.memory_extractor",
                  "nodes.retrieval_planner"]
_CONSUMERS = [import_module(name) for name in _CONSUMER_MODS]


@pytest.fixture(scope="module", autouse=True)
def _mock_llm_only_here():
    mock = MockLLM()
    mods = [m for m in _CONSUMERS if hasattr(m, "llm")]
    originals = [(m, m.llm) for m in mods]
    for m in mods:
        m.llm = mock
    yield
    for m, orig in originals:
        m.llm = orig


from graph import create_runnable_graph  # noqa: E402


def _run(question: str) -> dict:
    app = create_runnable_graph()
    return app.invoke({"question": question})


def _counts(state: dict) -> dict:
    trace = state.get("execution_trace", [])
    return {
        "planner_calls": sum(1 for tr in trace if str(tr.get("step", "")).startswith("planner")),
        "tool_steps": len([tr for tr in trace if tr.get("action") == "tool"]),
        "finals": len([tr for tr in trace if tr.get("action") == "final"]),
        "tool_call_count": state.get("tool_call_count", 0),
        "completed_steps": list(state.get("completed_steps", [])),
        "tool_results": list(state.get("tool_results", [])),
    }


@pytest.fixture(scope="module")
def calc_state():
    return _run("What is 128 divided by 8?")


def test_planner_call_count_matches_actual_invocations(calc_state):
    # calculator -> final == exactly 2 planner invocations
    c = _counts(calc_state)
    assert c["planner_calls"] == 2
    assert c["tool_steps"] == 1
    assert c["finals"] == 1


def test_tool_call_count_matches_executed_tools(calc_state):
    c = _counts(calc_state)
    assert c["tool_call_count"] == 1
    assert len(c["tool_results"]) == 1
    assert c["tool_results"][0]["tool"] == "calculator"


def test_completed_steps_contain_no_phantom_tools(calc_state):
    # completed_steps must reflect executed tools (+ pre-retrieval), nothing else
    c = _counts(calc_state)
    assert c["completed_steps"].count("calculator") == 1


def test_multistep_counters():
    # search then calculate -> 3 planner invocations, 2 tool executions
    state = _run("Find the population of Japan and calculate 0.5% of it.")
    c = _counts(state)
    assert c["planner_calls"] == 3
    assert c["finals"] == 1
    assert c["tool_call_count"] == 2
    tools_in_order = [r["tool"] for r in c["tool_results"]]
    assert tools_in_order == ["web_search", "calculator"]
