import json
import re
import time
import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from llm import llm
from .tools import tools
from config import MAX_TOOL_STEPS, TIMEOUT_LLM_S, LLM_PROVIDER, LLM_MODEL_OVERRIDE, MODEL_NAME

logger = logging.getLogger(__name__)

TOOL_INFO = "\n".join([f"- {t.name}: {t.description}\n  Schema: {t.args_schema.model_json_schema() if t.args_schema else 'None'}" for t in tools])
VALID_TOOL_NAMES = [t.name for t in tools]

class PlannerDecision(BaseModel):
    action: Literal["tool", "final"] = Field(description="Choose 'tool' to call a tool, or 'final' to provide the final answer.")
    tool: Optional[str] = Field(default=None, description=f"If action is 'tool', provide the exact name of the tool to call. Valid options: {VALID_TOOL_NAMES}")
    arguments: Optional[dict] = Field(default=None, description="If action is 'tool', provide a JSON object of arguments matching the tool's schema.")
    answer: Optional[str] = Field(default=None, description="If action is 'final', provide the final response to the user.")

PLANNER_SYSTEM_PROMPT = f"""You are a precise, reliable multi-step execution planner.
Your job is to analyze the user's query, any retrieved context, and all previous tool executions, then decide the SINGLE next action.

Available Tools:
{TOOL_INFO}

MANDATORY RULES:
1. Action Selection: You may only output 'action': 'tool' OR 'action': 'final'.
2. Tool Necessity - Arithmetic & Calculations:
   - If the user query requires ANY arithmetic, percentage, ratio, difference, multiplication, division, power/sqrt, or numerical computation, you MUST call the 'calculator' tool.
   - NEVER do mental math or calculate in your head. Always execute the calculation with the 'calculator' tool.
3. Tool Necessity - External Facts & Real-Time Lookups:
   - If the query asks for real-world entities, current facts, statistics, prices, populations, or external info NOT provided in 'RETRIEVED CONTEXT', you MUST call the 'web_search' tool.
4. Multi-Step Execution & Dependency:
   - For multi-step queries (e.g. search population then calculate 0.5%, or search two entities and compare/subtract them, or retrieve policy then multiply for 3 employees), execute each tool step one at a time.
   - Use the output from earlier steps to supply arguments to subsequent steps.
5. Multi-Step Completion Checklist (BEFORE RETURNING 'final'):
   - Review the original user query. List every operation explicitly requested.
   - Check 'PREVIOUS TOOL EXECUTIONS'. Have all requested lookups and calculations been executed via tools?
   - If ANY requested calculation or lookup is missing, you MUST NOT return 'final'. You MUST output 'action': 'tool' for the next missing operation.
   - Only return 'final' when ALL required operations have been executed and you have all facts to answer completely.
6. Pure Context Queries:
   - If 'RETRIEVED CONTEXT' contains the exact information needed AND NO arithmetic/calculation/search was requested, return 'action': 'final'.
"""

def check_completion_guard(question: str, completed_steps: list[str], tool_results: list[dict], context: str) -> tuple[bool, str]:
    q_lower = question.lower()
    calc_indicators = [
        "calculate", "multiply", "multiplied", "divide", "divided", "sum of",
        "subtract", "square root", "sqrt", "%", "percent", "ratio of", "ratio", "difference in",
        "difference between", "how much would", "how many are left", "have left", "remaining",
        "total amount if", "what is that divided", "what would", "times larger", "within budget",
        "difference", "in total", "stipend for", "team of"
    ]
    math_op_regex = re.search(r'\b\d+\s*[\+\-\*\/]\s*\d+\b', question)
    requires_calc = any(ind in q_lower for ind in calc_indicators) or bool(math_op_regex)
    if requires_calc and "calculator" not in completed_steps:
        return False, "Calculation requested in query has not been executed via calculator tool."
    search_indicators = [
        "who is", "what is the population", "current price", "stock price", "current ceo",
        "gdp of", "speed of light", "distance to", "distance from", "tallest building",
        "population of", "latest news", "release date", "retail price"
    ]
    requires_search = any(ind in q_lower for ind in search_indicators)
    has_retrieved_info = bool(context and len(context.strip()) > 30) or ("rag" in completed_steps) or ("web_search" in completed_steps)
    if requires_search and not has_retrieved_info:
        return False, "External factual lookup requested in query has not been executed via web_search tool."
    return True, ""

def is_repeated_tool_call(tool_name: str, tool_args: dict, tool_results: list[dict]) -> bool:
    if not tool_results:
        return False
    last_exec = tool_results[-1]
    if last_exec.get("tool") == tool_name and last_exec.get("arguments") == tool_args:
        return True
    return False

def _emit_planner_event(state: dict, dur_ms: int, decision: PlannerDecision | None, step: int, status: str = "success", extra: dict | None = None, error: dict | None = None):
    try:
        from observability.trace import make_event, append_event, add_latency, extract_llm_usage
        add_latency(state, "planner", dur_ms)
        meta = extra or {}
        meta.update({"planner_step": step, "latency_ms": dur_ms,
                     "provider": LLM_PROVIDER or "unknown", "model": LLM_MODEL_OVERRIDE or MODEL_NAME})
        if decision is not None:
            meta.update({"action": decision.action, "tool": decision.tool, "arguments": decision.arguments,
                         "answer_preview": (decision.answer or "")[:200] if decision.answer else None})
        ev = make_event(state, "PLANNER", "planner", duration_ms=dur_ms, status=status, metadata=meta, error=error)
        append_event(state, ev)
    except Exception:
        pass

def planner_node(state: dict) -> dict:
    t_start = time.perf_counter()
    question = state.get("question", "")
    context = state.get("_combined_context", "")
    messages = state.get("messages", [])
    
    tool_call_count = state.get("tool_call_count", 0)
    completed_steps = list(state.get("completed_steps", []))
    tool_results = list(state.get("tool_results", []))
    execution_trace = list(state.get("execution_trace", []))
    
    retrieval_plan = state.get("retrieval_plan", {})
    if retrieval_plan.get("rag") and "rag" not in completed_steps:
        completed_steps.insert(0, "rag")
    if (retrieval_plan.get("profile") or retrieval_plan.get("semantic")) and "memory_search" not in completed_steps:
        completed_steps.insert(0, "memory_search")

    if context:
        user_prompt = f"RETRIEVED CONTEXT:\n{context}\n\nUser Query: {question}"
    else:
        user_prompt = f"User Query: {question}"
        
    if messages and messages[-1].type == "tool":
        last_tool_msg = messages[-1]
        if len(messages) >= 2 and messages[-2].type == "ai":
            last_ai_msg = messages[-2]
            if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
                call = last_ai_msg.tool_calls[0]
                tool_name = call["name"]
                tool_args = call["args"]
                if len(tool_results) < tool_call_count:
                    if tool_name not in completed_steps or completed_steps.count(tool_name) < tool_call_count:
                        completed_steps.append(tool_name)
                    tool_results.append({"tool": tool_name, "arguments": tool_args, "result": last_tool_msg.content})

    if tool_results:
        history_str = "PREVIOUS TOOL EXECUTIONS:\n"
        for i, res in enumerate(tool_results):
            history_str += f"\nStep {i+1}: Called '{res.get('tool')}'\n"
            history_str += f"Arguments: {json.dumps(res.get('arguments', {}))}\n"
            history_str += f"Result: {res.get('result', 'Error/No Result')}\n"
        user_prompt = f"{history_str}\n\n{user_prompt}"

    structured_llm = llm.with_structured_output(PlannerDecision)
    
    t_llm_start = time.perf_counter()
    try:
        from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
        def _call_llm():
            return structured_llm.invoke([SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=user_prompt)])
        try:
            decision = run_with_timeout(_call_llm, TIMEOUT_LLM_S)
        except ObsTimeout as te:
            t_llm_end = time.perf_counter()
            llm_latency = round(t_llm_end - t_llm_start, 3)
            execution_trace.append({"step": "planner_error", "latency_s": llm_latency, "error": str(te)})
            try:
                from observability.errors import make_error_payload, ErrorType
                from observability.trace import make_event, append_event
                err = make_error_payload(ErrorType.TIMEOUT_ERROR.value, "planner", str(te), trace_id=state.get("trace_id"))
                ev = make_event(state, "TIMEOUT", "planner", duration_ms=int(llm_latency*1000), status="timeout",
                                metadata={"timeout_s": TIMEOUT_LLM_S}, error=err)
                append_event(state, ev)
                _emit_planner_event(state, int(llm_latency*1000), None, tool_call_count+1, status="timeout",
                                    extra={"validation_result": "timeout", "error": str(te)[:300]}, error=err)
            except Exception:
                pass
            return {"answer": "I'm sorry, the planner timed out while thinking. Please try again.",
                    "execution_status": "timeout", "execution_trace": execution_trace,
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}
    except Exception as e:
        t_llm_end = time.perf_counter()
        logger.error(f"Planner failed to generate structured output: {e}")
        execution_trace.append({"step": "planner_error", "latency_s": round(t_llm_end - t_llm_start, 3), "error": str(e)})
        try:
            from observability.errors import classify_error, make_error_payload
            err_type = classify_error(e, component="planner")
            err = make_error_payload(err_type, "planner", str(e), trace_id=state.get("trace_id"))
            _emit_planner_event(state, int((t_llm_end - t_llm_start)*1000), None, tool_call_count+1, status="error",
                                extra={"validation_result": "error", "error": str(e)[:300]}, error=err)
        except Exception:
            pass
        return {"answer": "I'm sorry, I encountered an internal error while planning the next step.",
                "execution_status": "error", "execution_trace": execution_trace,
                "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                "latency_breakdown": state.get("latency_breakdown")}
    t_llm_end = time.perf_counter()
    llm_latency = round(t_llm_end - t_llm_start, 3)

    # record llm usage
    try:
        from observability.trace import extract_llm_usage
        # decision is a Pydantic object; the raw response is not captured, but we estimate
        if state.get("llm_usage") is None:
            state["llm_usage"] = []
        # try to capture from structured output — not always available, use placeholder
        state["llm_usage"].append({"node": "planner", "provider": LLM_PROVIDER or "unknown",
                                   "model": LLM_MODEL_OVERRIDE or MODEL_NAME,
                                   "latency_ms": int(llm_latency*1000), "step": tool_call_count+1})
    except Exception:
        pass

    if decision.action == "tool":
        if is_repeated_tool_call(decision.tool, decision.arguments or {}, tool_results):
            logger.warning(f"Repeated tool call loop detected: {decision.tool} with {decision.arguments}")
            execution_trace.append({"step": f"planner_{tool_call_count+1}", "decision": "repeated_tool_call_loop", "llm_latency_s": llm_latency})
            _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="error",
                                extra={"validation_result": "repeated_tool_call_loop"})
            return {"answer": "Task terminated to prevent repeated execution of the same tool without new information.",
                    "execution_status": "repeated_tool_call", "tool_loop_detected": True,
                    "completed_steps": completed_steps, "tool_results": tool_results,
                    "execution_trace": execution_trace,
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage")}

    if decision.action == "final":
        is_complete, guard_reason = check_completion_guard(question, completed_steps, tool_results, context)
        if not is_complete and tool_call_count < MAX_TOOL_STEPS:
            logger.info(f"Completion guard triggered: {guard_reason}. Prompting planner for missing step.")
            guard_prompt = f"{user_prompt}\n\n[GUARD NOTICE]: You attempted to finalize the task, but: {guard_reason}. You MUST execute the required tool first."
            try:
                from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
                def _call_guard():
                    return structured_llm.invoke([SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=guard_prompt)])
                try:
                    decision = run_with_timeout(_call_guard, TIMEOUT_LLM_S)
                except ObsTimeout:
                    pass
                else:
                    # record guard as validation
                    try:
                        _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="success",
                                            extra={"validation_result": f"guard_triggered: {guard_reason}", "guard_reason": guard_reason})
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Planner re-prompt failed: {e}")

    if decision.action == "tool":
        if decision.tool not in VALID_TOOL_NAMES:
            logger.warning(f"Planner hallucinated tool: {decision.tool}")
            try:
                from observability.errors import make_error_payload, ErrorType
                err = make_error_payload(ErrorType.TOOL_SELECTION_ERROR.value, "planner",
                                         f"hallucinated tool {decision.tool}", trace_id=state.get("trace_id"))
                _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="error",
                                    extra={"validation_result": "invalid_tool"}, error=err)
            except Exception:
                pass
            return {"answer": f"I tried to use an invalid tool: {decision.tool}. I cannot complete the request.",
                    "execution_status": "error", "execution_trace": execution_trace,
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}
            
        tool_call_id = f"call_{tool_call_count}"
        tool_call = {"name": decision.tool, "args": decision.arguments or {}, "id": tool_call_id}
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        execution_trace.append({"step": f"planner_{tool_call_count+1}", "action": "tool", "tool": decision.tool, "arguments": decision.arguments, "llm_latency_s": llm_latency})
        _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="success",
                            extra={"validation_result": "ok"})
        new_state = {"messages": [ai_msg], "current_step": decision.tool, "last_action": decision.tool,
                     "tool_call_count": tool_call_count + 1, "execution_status": "running",
                     "completed_steps": completed_steps, "tool_results": tool_results,
                     "execution_trace": execution_trace,
                     "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                     "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage")}
        return new_state
        
    else:
        answer = decision.answer or "Task complete."
        execution_trace.append({"step": f"planner_{tool_call_count+1}", "action": "final", "llm_latency_s": llm_latency})
        _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="success",
                            extra={"validation_result": "final"})
        new_state = {"messages": [AIMessage(content=answer)], "answer": answer, "last_action": "final",
                     "execution_status": "completed", "completed_steps": completed_steps,
                     "tool_results": tool_results, "execution_trace": execution_trace,
                     "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                     "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage")}
        return new_state
