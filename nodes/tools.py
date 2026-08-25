"""
Tools & Tool Node — with observability, timeout, retry, circuit-breaker, redaction.
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

tools = [web_search_tool, calculator]
tool_node_raw = ToolNode(tools)
_tool_map = {t.name: t for t in tools}

def run_tool(tool_name: str, tool_input: dict) -> str:
    tool = _tool_map.get(tool_name)
    if tool is None:
        return f"Unknown tool: {tool_name}"
    try:
        return str(tool.invoke(tool_input))
    except Exception as e:
        return f"Error running tool '{tool_name}': {e}"

# ---- traced tool_node that LangGraph will call ----
def tool_node(state: dict) -> dict:
    """Execute tools with tracing, timeout, retry, redaction, circuit-breaker."""
    import time as _time
    from config import TIMEOUT_WEB_SEARCH_S, TIMEOUT_TOOL_S, MAX_TOOL_FAILURES_PER_TOOL
    from observability.trace import make_event, append_event, add_latency
    from observability.redaction import summarize_tool_result, safe_serialize
    from observability.errors import classify_error, make_error_payload, ErrorType
    from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
    from observability.retry import call_with_retry

    messages = state.get("messages", [])
    if not messages:
        return {}
    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None) or []
    if not tool_calls:
        # fallback: try to parse from content
        return tool_node_raw.invoke(state)

    outputs = []
    for call in tool_calls:
        tool_name = call.get("name") or call.get("tool") or "unknown"
        tool_args = call.get("args") or call.get("arguments") or {}
        tool_id = call.get("id") or f"call_{int(_time.time()*1000)}"

        # circuit breaker check
        counts = state.get("tool_failure_counts") or {}
        if counts.get(tool_name, 0) >= MAX_TOOL_FAILURES_PER_TOOL:
            err_payload = make_error_payload(ErrorType.TOOL_EXECUTION_ERROR.value, "tools",
                                             f"circuit open: too many failures for {tool_name}",
                                             retryable=False, trace_id=state.get("trace_id"))
            ev = make_event(state, "ERROR", "tools", status="error",
                            metadata={"tool": tool_name, "circuit_breaker": "open"}, error=err_payload)
            append_event(state, ev)
            result_str = f"Error: circuit breaker open for tool '{tool_name}' after {counts[tool_name]} failures"
            outputs.append(ToolMessage(content=result_str, tool_call_id=tool_id, name=tool_name))
            continue

        # choose timeout per tool
        timeout_s = TIMEOUT_WEB_SEARCH_S if tool_name == "web_search" else TIMEOUT_TOOL_S

        def _execute():
            # for timeout wrapper, run the raw tool
            tool_obj = _tool_map.get(tool_name)
            if tool_obj is None:
                raise ValueError(f"Unknown tool: {tool_name}")
            # validate args roughly
            return str(tool_obj.invoke(tool_args))

        t0 = _time.perf_counter()
        status = "success"
        err_payload = None
        result_str = ""
        try:
            # decide if retry is allowed (web_search yes, calculator no)
            if tool_name == "web_search":
                from config import MAX_RETRIES
                def _with_timeout():
                    return run_with_timeout(_execute, timeout_s)
                result_str = call_with_retry(_with_timeout, component="tools", state=state, max_retries=MAX_RETRIES)
            else:
                # calculator: no retry (deterministic)
                result_str = run_with_timeout(_execute, timeout_s)
            # check if result is error string (tool returned error, not exception)
            if isinstance(result_str, str) and result_str.lower().startswith("error"):
                # classify as tool execution error but not retryable for calculator
                if tool_name != "calculator":
                    # web_search error string may be retryable? treat as tool execution
                    pass
        except Exception as exc:
            # classify
            if isinstance(exc, ObsTimeout):
                err_type = ErrorType.TIMEOUT_ERROR.value
                err_payload = make_error_payload(err_type, "tools", str(exc), trace_id=state.get("trace_id"))
                status = "timeout"
                result_str = f"Error: timeout after {timeout_s}s for tool '{tool_name}'"
                ev = make_event(state, "TIMEOUT", "tools", duration_ms=int((_time.perf_counter()-t0)*1000),
                                status="timeout", metadata={"tool": tool_name, "timeout_s": timeout_s}, error=err_payload)
                append_event(state, ev)
            else:
                err_type = classify_error(exc, component="tools")
                err_payload = make_error_payload(err_type, "tools", str(exc), trace_id=state.get("trace_id"))
                status = "error"
                result_str = f"Error: {exc}"
            # increment failure count
            if state.get("tool_failure_counts") is None:
                state["tool_failure_counts"] = {}
            state["tool_failure_counts"][tool_name] = state["tool_failure_counts"].get(tool_name, 0) + 1
        else:
            # success path: check for error string increment
            if isinstance(result_str, str) and result_str.lower().startswith("error"):
                # still count as failure for circuit breaker but not exception
                if state.get("tool_failure_counts") is None:
                    state["tool_failure_counts"] = {}
                # only count web_search errors as failures, calculator errors are validation not infra
                if tool_name == "web_search":
                    state["tool_failure_counts"][tool_name] = state["tool_failure_counts"].get(tool_name, 0) + 1
                err_type = ErrorType.TOOL_EXECUTION_ERROR.value if tool_name == "web_search" else ErrorType.VALIDATION_ERROR.value
                err_payload = make_error_payload(err_type, "tools", result_str, trace_id=state.get("trace_id"))
                status = "error"
            else:
                status = "success"

        dur_ms = int((_time.perf_counter() - t0) * 1000)
        add_latency(state, f"tool:{tool_name}", dur_ms)
        add_latency(state, "tools", dur_ms)

        # emit TOOL_CALL and TOOL_RESULT
        try:
            ev_call = make_event(state, "TOOL_CALL", "tools", duration_ms=dur_ms, status=status,
                                 metadata={"tool": tool_name, "arguments": safe_serialize(tool_args),
                                           "tool_call_id": tool_id, "timeout_s": timeout_s},
                                 error=err_payload if status != "success" else None)
            append_event(state, ev_call)
            summ = summarize_tool_result(tool_name, result_str)
            ev_res = make_event(state, "TOOL_RESULT", "tools", duration_ms=0, status=status,
                                metadata={"tool": tool_name, "result_summary": summ, "is_error": status != "success"},
                                error=err_payload if status != "success" else None)
            append_event(state, ev_res)
        except Exception:
            pass

        outputs.append(ToolMessage(content=result_str, tool_call_id=tool_id, name=tool_name))

    # also track overall tool latency
    if outputs:
        return {"messages": outputs, "trace_events": state.get("trace_events"),
                "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown"),
                "tool_failure_counts": state.get("tool_failure_counts"),
                "tool_results": state.get("tool_results")}  # planner will later append
    return {}
