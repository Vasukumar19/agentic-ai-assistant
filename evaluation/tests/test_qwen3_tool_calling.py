"""
Real Qwen3 tool-calling tests.

Runs ONLY when LLM_PROVIDER=ollama. Validates that Qwen3 produces real
bind_tools() tool calls and that the tools actually execute.
"""

import importlib

import pytest
from langchain_core.messages import HumanMessage

import llm as llm_module


def _ensure_real_llm():
    """If an earlier test module cached MockLLM in sys.modules, reload the
    real provider so this test exercises actual model execution."""
    if type(llm_module.llm).__name__ == "MockLLM":
        importlib.reload(llm_module)
    return llm_module.llm


llm = _ensure_real_llm()

from nodes.tools import tools, run_tool  # noqa: E402

pytestmark = pytest.mark.skipif(
    type(llm).__name__ != "ChatOllama",
    reason="Requires the real Ollama provider (LLM_PROVIDER=ollama)",
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
    # Upstream DuckDuckGo backend has intermittent DNS/network failures that are
    # unrelated to the model or our stack; report them as skips, not failures.
    lowered = out.lower()
    if "error" in lowered and ("connect" in lowered or "dns" in lowered or "timed out" in lowered):
        pytest.skip(f"Upstream search backend unavailable: {out[:120]}")
    assert isinstance(out, str) and len(out) > 50
    assert not out.startswith("Error running tool")
