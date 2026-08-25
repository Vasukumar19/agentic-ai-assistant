"""
Real Qwen3 tool-calling tests.

Runs ONLY when LLM_PROVIDER=ollama. Validates that Qwen3 produces real
bind_tools() tool calls and that the tools actually execute.
"""

import os

import pytest
from langchain_core.messages import HumanMessage

from llm import llm
from nodes.tools import tools, run_tool

pytestmark = pytest.mark.skipif(
    os.getenv("LLM_PROVIDER", "").lower() != "ollama",
    reason="Requires LLM_PROVIDER=ollama",
)


def test_bind_tools_produces_real_calculator_call():
    bound = llm.bind_tools(tools)
    msg = bound.invoke([HumanMessage(content="What is 128 / 8?")])
    assert msg.tool_calls, "Model did not emit a native tool call"
    call = msg.tool_calls[0]
    assert call["name"] == "calculator"
    assert "8" in str(call["args"])


def test_calculator_tool_executes():
    out = run_tool("calculator", {"expression": "128 / 8"})
    assert out.strip() == "16.0"


def test_web_search_tool_executes():
    out = run_tool("web_search", {"query": "current population of Japan"})
    assert isinstance(out, str) and len(out) > 50
    assert not out.startswith("Error running tool")
