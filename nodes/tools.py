"""
Tools & Tool Node
=================

Defines available tools (web_search, calculator) and ToolNode for execution.

Note: Memory and RAG retrieval are NOT tools - they're handled by graph nodes.
"""

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from asteval import Interpreter


# Tool 1: Web Search
web_search_tool = DuckDuckGoSearchRun(
    name="web_search",
    description=(
        "Search the web using DuckDuckGo for current events, news, or external information. "
        "Use for recent data that may have changed after training. "
        "Input: search query string."
    ),
)


# Tool 2: Calculator
@tool
def calculator(expression: str) -> str:
    """
    Evaluate arithmetic expressions: +, -, *, /, **, sqrt, sin, cos, etc.
    Use for mathematical calculations.
    Examples: '2 + 2', 'sqrt(144)', '100 * 3.14', '2 ** 10'
    """
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
    Execute a specific tool and return result.
    
    Args:
        tool_name: Name of the tool to run
        tool_input: Input to the tool
    
    Returns:
        String result from tool
    """
    if tool_name == "web_search":
        return web_search_tool.run(tool_input)
    elif tool_name == "calculator":
        return calculator(tool_input)
    else:
        return f"Unknown tool: {tool_name}"
