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

os.environ["MOCK_LLM"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from graph import create_runnable_graph  # noqa: E402

# Restore immediately: llm singleton is already built; leaving this set would
# poison sys.modules' cached llm for other test modules in the same session.
os.environ.pop("MOCK_LLM", None)


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
