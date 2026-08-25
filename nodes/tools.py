"""
Tools & Tool Node — with observability, timeout, retry, circuit-breaker, redaction.
Native + MCP via ToolRegistry.
"""

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool, StructuredTool
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field
from langgraph.prebuilt import ToolNode
from asteval import Interpreter
import time
import logging

logger = logging.getLogger(__name__)

class WebSearchInput(BaseModel):
    query: str = Field(description="The search query as a plain string, e.g. 'latest AI news'. Avoid apostrophes/quotes where possible.")

_ddg_search = DuckDuckGoSearchRun()

def _web_search_fn(query: str) -> str:
    return _ddg_search.run(query)

web_search_tool = StructuredTool.from_function(
    func=_web_search_fn,
    name="web_search",
    description="Search the web for current events, news, or external information not in your training data.",
    args_schema=WebSearchInput,
)

class CalculatorInput(BaseModel):
    expression: str = Field(description="A math expression to evaluate, e.g. '2 + 2', 'sqrt(144)', '100 * 3.14', '2 ** 10'.")

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

# ---- registry bootstrap ----
try:
    from mcp_layer.registry import registry
    # register native tools (idempotent — guard against double-register on reload)
    if "web_search" not in registry.valid_names():
        registry.register_native(web_search_tool)
    if "calculator" not in registry.valid_names():
        registry.register_native(calculator)
except Exception as e:
    logger.warning(f"registry bootstrap failed: {e}")
    from mcp_layer.registry import registry  # type: ignore

# backward-compat export: tools is dynamic via registry
# keep as property-like list for imports that expect `from nodes.tools import tools`
def _get_tools():
    try:
        return registry.all_tools()
    except Exception:
        return [web_search_tool, calculator]

tools = _get_tools()
_tool_map = {t.name: t for t in tools}
tool_node_raw = ToolNode(tools)

def _refresh_tool_node():
    """Refresh global tool_node_raw after MCP discovery."""
    global tools, _tool_map, tool_node_raw
    try:
        tools = registry.all_tools()
        _tool_map = registry.tool_map()
        tool_node_raw = ToolNode(tools)
    except Exception as e:
        logger.warning(f"refresh tool node failed: {e}")

def _current_tool_map():
    try:
        return registry.tool_map()
    except Exception:
        return _tool_map

def run_tool(tool_name: str, tool_input: dict) -> str:
    m = _current_tool_map()
    t = m.get(tool_name)
    if t is None:
        return f"Unknown tool: {tool_name}"
    try:
        return str(t.invoke(tool_input))
    except Exception as e:
        return f"Error running tool '{tool_name}': {e}"

def requires_confirmation(tool_name: str, arguments: dict | None = None) -> bool:
    """Backend hook — does this tool require human confirmation?"""
    try:
        return registry.requires_confirmation(tool_name, arguments)
    except Exception:
        return False

# ---- traced tool_node that LangGraph will call ----
def tool_node(state: dict) -> dict:
    """Execute tools with tracing, timeout, retry, redaction, circuit-breaker, MCP handling."""
    import time as _time
    from config import TIMEOUT_WEB_SEARCH_S, TIMEOUT_TOOL_S, TIMEOUT_MCP_S, MAX_TOOL_FAILURES_PER_TOOL
    from observability.trace import make_event, append_event, add_latency
    from observability.redaction import summarize_tool_result, safe_serialize
    from observability.errors import classify_error, make_error_payload, ErrorType
    from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
    from observability.retry import call_with_retry

    # ensure MCP discovery has run (lazy)
    try:
        if not registry._discovered and registry._servers:
            # no servers configured — no-op
            pass
        elif not registry._discovered:
            # try to discover from env (may be empty)
            registry.discover()
            _refresh_tool_node()
    except Exception:
        pass

    messages = state.get("messages", [])
    if not messages:
        return {}
    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None) or []
    if not tool_calls:
        return tool_node_raw.invoke(state)

    outputs = []
    for call in tool_calls:
        tool_name = call.get("name") or call.get("tool") or "unknown"
        tool_args = call.get("args") or call.get("arguments") or {}
        tool_id = call.get("id") or f"call_{int(_time.time()*1000)}"

        # human confirmation hook for MCP destructive/write tools
        if requires_confirmation(tool_name, tool_args):
            from observability.errors import ErrorType as EType
            err_payload = make_error_payload(EType.TOOL_EXECUTION_ERROR.value, "tools",
                                             f"tool {tool_name} requires confirmation", retryable=False, trace_id=state.get("trace_id"))
            ev = make_event(state, "MCP_TOOL_CALL", "tools", status="error",
                            metadata={"tool": tool_name, "requires_confirmation": True, "server": (registry.get_normalized(tool_name).server if registry.get_normalized(tool_name) else None)},
                            error=err_payload)
            append_event(state, ev)
            # do NOT execute
            return {"answer": f"Tool '{tool_name}' requires confirmation before execution.",
                    "execution_status": "awaiting_confirmation",
                    "trace_events": state.get("trace_events"),
                    "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown")}

        # circuit breaker
        counts = state.get("tool_failure_counts") or {}
        if counts.get(tool_name, 0) >= MAX_TOOL_FAILURES_PER_TOOL:
            err_payload = make_error_payload(ErrorType.TOOL_EXECUTION_ERROR.value, "tools",
                                             f"circuit open: too many failures for {tool_name}", retryable=False, trace_id=state.get("trace_id"))
            ev = make_event(state, "ERROR", "tools", status="error",
                            metadata={"tool": tool_name, "circuit_breaker": "open"}, error=err_payload)
            append_event(state, ev)
            result_str = f"Error: circuit breaker open for tool '{tool_name}' after {counts[tool_name]} failures"
            outputs.append(ToolMessage(content=result_str, tool_call_id=tool_id, name=tool_name))
            continue

        is_mcp = False
        try:
            is_mcp = registry.is_mcp_tool(tool_name)
        except Exception:
            pass

        if is_mcp:
            timeout_s = TIMEOUT_MCP_S
            # observability: distinguish MCP
            source = "mcp"
            server = (registry.get_normalized(tool_name).server if registry.get_normalized(tool_name) else "unknown")
        elif tool_name == "web_search":
            timeout_s = TIMEOUT_WEB_SEARCH_S
            source = "native"
            server = None
        else:
            timeout_s = TIMEOUT_TOOL_S
            source = "native"
            server = None

        def _execute():
            m = _current_tool_map()
            obj = m.get(tool_name)
            if obj is None:
                raise ValueError(f"Unknown tool: {tool_name}")
            return str(obj.invoke(tool_args))

        t0 = _time.perf_counter()
        status = "success"
        err_payload = None
        result_str = ""
        try:
            if is_mcp or tool_name == "web_search":
                from config import MAX_RETRIES
                def _with_timeout():
                    return run_with_timeout(_execute, timeout_s)
                result_str = call_with_retry(_with_timeout, component="tools", state=state, max_retries=MAX_RETRIES)
            else:
                result_str = run_with_timeout(_execute, timeout_s)
            if isinstance(result_str, str) and result_str.lower().startswith("error"):
                pass
        except Exception as exc:
            # map MCP errors to taxonomy
            try:
                from mcp_layer.errors import MCPError as MCPExc
                if isinstance(exc, MCPExc):
                    mcp_code = exc.code
                    from mcp_layer.errors import mcp_error_type_to_observability
                    err_type = mcp_code  # keep MCP code for event
                    obs_type = mcp_error_type_to_observability(mcp_code)
                    # emit MCP_ERROR
                    mcp_err = make_error_payload(obs_type, "tools", str(exc), trace_id=state.get("trace_id"))
                    ev_mcp = make_event(state, "MCP_ERROR", "tools", status="error",
                                        metadata={"tool": tool_name, "server": server, "mcp_code": mcp_code, "source": source},
                                        error=mcp_err)
                    append_event(state, ev_mcp)
                    # also classify for retry logic
                    if mcp_code == "MCP_TIMEOUT":
                        err_payload = make_error_payload(ErrorType.TIMEOUT_ERROR.value, "tools", str(exc), trace_id=state.get("trace_id"))
                        status = "timeout"
                        result_str = f"Error: timeout after {timeout_s}s for tool '{tool_name}'"
                        ev = make_event(state, "TIMEOUT", "tools", duration_ms=int((_time.perf_counter()-t0)*1000),
                                        status="timeout", metadata={"tool": tool_name, "timeout_s": timeout_s, "source": source, "server": server}, error=err_payload)
                        append_event(state, ev)
                    else:
                        err_payload = mcp_err
                        status = "error"
                        result_str = f"Error: {exc}"
                elif isinstance(exc, ObsTimeout):
                    err_type = ErrorType.TIMEOUT_ERROR.value
                    err_payload = make_error_payload(err_type, "tools", str(exc), trace_id=state.get("trace_id"))
                    status = "timeout"
                    result_str = f"Error: timeout after {timeout_s}s for tool '{tool_name}'"
                    ev = make_event(state, "TIMEOUT" if not is_mcp else "MCP_TIMEOUT", "tools", duration_ms=int((_time.perf_counter()-t0)*1000),
                                    status="timeout", metadata={"tool": tool_name, "timeout_s": timeout_s, "source": source, "server": server}, error=err_payload)
                    append_event(state, ev)
                else:
                    err_type = classify_error(exc, component="tools")
                    err_payload = make_error_payload(err_type, "tools", str(exc), trace_id=state.get("trace_id"))
                    status = "error"
                    result_str = f"Error: {exc}"
            except Exception:
                err_payload = make_error_payload(ErrorType.UNKNOWN_ERROR.value, "tools", str(exc), trace_id=state.get("trace_id"))
                status = "error"
                result_str = f"Error: {exc}"
            if state.get("tool_failure_counts") is None:
                state["tool_failure_counts"] = {}
            state["tool_failure_counts"][tool_name] = state["tool_failure_counts"].get(tool_name, 0) + 1
        else:
            if isinstance(result_str, str) and result_str.lower().startswith("error"):
                if state.get("tool_failure_counts") is None:
                    state["tool_failure_counts"] = {}
                if tool_name == "web_search" or is_mcp:
                    state["tool_failure_counts"][tool_name] = state["tool_failure_counts"].get(tool_name, 0) + 1
                # MCP error strings already handled via exception path; this is fallback
                if err_payload is None:
                    err_type = ErrorType.TOOL_EXECUTION_ERROR.value if (tool_name == "web_search" or is_mcp) else ErrorType.VALIDATION_ERROR.value
                    err_payload = make_error_payload(err_type, "tools", result_str, trace_id=state.get("trace_id"))
                status = "error"
            else:
                status = "success"

        dur_ms = int((_time.perf_counter() - t0) * 1000)
        add_latency(state, f"tool:{tool_name}", dur_ms)
        add_latency(state, "tools", dur_ms)

        try:
            ev_type_call = "MCP_TOOL_CALL" if is_mcp else "TOOL_CALL"
            ev_type_res = "MCP_TOOL_RESULT" if is_mcp else "TOOL_RESULT"
            meta_call = {"tool": tool_name, "arguments": safe_serialize(tool_args), "tool_call_id": tool_id, "timeout_s": timeout_s, "source": source}
            if server:
                meta_call["server"] = server
            ev_call = make_event(state, ev_type_call, "tools", duration_ms=dur_ms, status=status, metadata=meta_call, error=err_payload if status != "success" else None)
            append_event(state, ev_call)
            summ = summarize_tool_result(tool_name, result_str)
            meta_res = {"tool": tool_name, "result_summary": summ, "is_error": status != "success", "source": source}
            if server:
                meta_res["server"] = server
            ev_res = make_event(state, ev_type_res, "tools", duration_ms=0, status=status, metadata=meta_res, error=err_payload if status != "success" else None)
            append_event(state, ev_res)
        except Exception:
            pass
        outputs.append(ToolMessage(content=result_str, tool_call_id=tool_id, name=tool_name))

    if outputs:
        return {"messages": outputs, "trace_events": state.get("trace_events"),
                "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown"),
                "tool_failure_counts": state.get("tool_failure_counts"), "tool_results": state.get("tool_results")}
    return {}
