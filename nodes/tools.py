"""
Tools & Tool Node
=================

Defines available tools (web_search, calculator) and ToolNode for execution.

Note: Memory and RAG retrieval are NOT tools - they're handled by graph nodes.
"""

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool, StructuredTool
from pydantic import BaseModel, Field
from langgraph.prebuilt import ToolNode
from asteval import Interpreter


# ---------------------------------------------------------------------------
# Tool 1: Web Search
# ---------------------------------------------------------------------------
# Wrap DuckDuckGoSearchRun with an explicit, strict args_schema instead of
# relying on the auto-generated one. A tight schema + short description
# noticeably improves Groq/Llama tool-calling reliability.

class WebSearchInput(BaseModel):
    query: str = Field(
        description="The search query as a plain string, e.g. 'latest AI news'. "
                     "Avoid apostrophes/quotes where possible (e.g. use 'todays news' not 'today's news')."
    )


_ddg_search = DuckDuckGoSearchRun()


def _web_search_fn(query: str) -> str:
    return _ddg_search.run(query)


web_search_tool = StructuredTool.from_function(
    func=_web_search_fn,
    name="web_search",
    description="Search the web for current events, news, or external information not in your training data.",
    args_schema=WebSearchInput,
)


# ---------------------------------------------------------------------------
# Tool 2: Calculator
# ---------------------------------------------------------------------------
class CalculatorInput(BaseModel):
    expression: str = Field(
        description="A math expression to evaluate, e.g. '2 + 2', 'sqrt(144)', '100 * 3.14', '2 ** 10'."
    )


@tool("calculator", args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """Evaluate arithmetic expressions: +, -, *, /, **, sqrt, sin, cos, etc."""
    try:
        aeval = Interpreter()
        result = aeval(expression)
        if aeval.error:
            return f"Error: {aeval.error[0].get_error()}"
        return str(result)
    except Exception as e:
        return f"Error: {e}"


# Tool list (only web_search and calculator)
tools = [web_search_tool, calculator]

# ToolNode for executing tools
tool_node = ToolNode(tools)


def run_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a specific tool directly and return its result.

    Args:
        tool_name: Name of the tool to run
        tool_input: Dict of args matching the tool's schema

    Returns:
        String result from tool
    """
    tool_map = {t.name: t for t in tools}
    tool = tool_map.get(tool_name)
    if tool is None:
        return f"Unknown tool: {tool_name}"
    try:
        return str(tool.invoke(tool_input))
    except Exception as e:
        return f"Error running tool '{tool_name}': {e}"