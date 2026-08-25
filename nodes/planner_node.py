import json
import re
import time
import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from llm import llm
from .tools import tools
from config import MAX_TOOL_STEPS

logger = logging.getLogger(__name__)

# Build a list of valid tool names and their schemas for the prompt
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
    """
    Zero-LLM deterministic completion check.
    Returns (is_complete, reason_if_incomplete).
    """
    q_lower = question.lower()
    
    # 1. Calculation Guard
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
        
    # 2. Search / External Info Guard
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

def planner_node(state: dict) -> dict:
    t_start = time.perf_counter()
    question = state.get("question", "")
    context = state.get("_combined_context", "")
    messages = state.get("messages", [])
    
    # Initialize execution state variables if they don't exist
    tool_call_count = state.get("tool_call_count", 0)
    completed_steps = list(state.get("completed_steps", []))
    tool_results = list(state.get("tool_results", []))
    execution_trace = list(state.get("execution_trace", []))
    
    # Include pre-retrieval RAG in completed_steps if present
    retrieval_plan = state.get("retrieval_plan", {})
    if retrieval_plan.get("rag") and "rag" not in completed_steps:
        completed_steps.insert(0, "rag")
    if (retrieval_plan.get("profile") or retrieval_plan.get("semantic")) and "memory_search" not in completed_steps:
        completed_steps.insert(0, "memory_search")

    if context:
        user_prompt = f"RETRIEVED CONTEXT:\n{context}\n\nUser Query: {question}"
    else:
        user_prompt = f"User Query: {question}"
        
    # First, update tool_results if the last message was a ToolMessage
    if messages and messages[-1].type == "tool":
        last_tool_msg = messages[-1]
        if len(messages) >= 2 and messages[-2].type == "ai":
            last_ai_msg = messages[-2]
            if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
                call = last_ai_msg.tool_calls[0]
                tool_name = call["name"]
                tool_args = call["args"]
                
                # Check if this tool result has already been recorded
                if len(tool_results) < tool_call_count:
                    if tool_name not in completed_steps or completed_steps.count(tool_name) < tool_call_count:
                        completed_steps.append(tool_name)
                    tool_results.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": last_tool_msg.content
                    })

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
        decision = structured_llm.invoke([
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ])
    except Exception as e:
        t_llm_end = time.perf_counter()
        logger.error(f"Planner failed to generate structured output: {e}")
        execution_trace.append({
            "step": "planner_error",
            "latency_s": round(t_llm_end - t_llm_start, 3),
            "error": str(e)
        })
        return {
            "answer": "I'm sorry, I encountered an internal error while planning the next step.",
            "execution_status": "error",
            "execution_trace": execution_trace
        }
    t_llm_end = time.perf_counter()
    llm_latency = round(t_llm_end - t_llm_start, 3)

    # ── Check Repeated Tool Call Loop ──────────────────────────────────────────
    if decision.action == "tool":
        if is_repeated_tool_call(decision.tool, decision.arguments or {}, tool_results):
            logger.warning(f"Repeated tool call loop detected: {decision.tool} with {decision.arguments}")
            execution_trace.append({
                "step": f"planner_{tool_call_count+1}",
                "decision": "repeated_tool_call_loop",
                "llm_latency_s": llm_latency,
            })
            return {
                "answer": "Task terminated to prevent repeated execution of the same tool without new information.",
                "execution_status": "repeated_tool_call",
                "tool_loop_detected": True,
                "completed_steps": completed_steps,
                "tool_results": tool_results,
                "execution_trace": execution_trace
            }

    # ── Deterministic Completion Guard ─────────────────────────────────────────
    if decision.action == "final":
        is_complete, guard_reason = check_completion_guard(question, completed_steps, tool_results, context)
        if not is_complete and tool_call_count < MAX_TOOL_STEPS:
            logger.info(f"Completion guard triggered: {guard_reason}. Prompting planner for missing step.")
            # Re-prompt planner with guard feedback
            guard_prompt = f"{user_prompt}\n\n[GUARD NOTICE]: You attempted to finalize the task, but: {guard_reason}. You MUST execute the required tool first."
            try:
                decision = structured_llm.invoke([
                    SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                    HumanMessage(content=guard_prompt)
                ])
            except Exception as e:
                logger.error(f"Planner re-prompt failed: {e}")

    # Handle Tool Action
    if decision.action == "tool":
        if decision.tool not in VALID_TOOL_NAMES:
            logger.warning(f"Planner hallucinated tool: {decision.tool}")
            return {
                "answer": f"I tried to use an invalid tool: {decision.tool}. I cannot complete the request.",
                "execution_status": "error",
                "execution_trace": execution_trace
            }
            
        tool_call_id = f"call_{tool_call_count}"
        tool_call = {
            "name": decision.tool,
            "args": decision.arguments or {},
            "id": tool_call_id
        }
        
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        
        execution_trace.append({
            "step": f"planner_{tool_call_count+1}",
            "action": "tool",
            "tool": decision.tool,
            "arguments": decision.arguments,
            "llm_latency_s": llm_latency,
        })
        
        new_state = {
            "messages": [ai_msg],
            "current_step": decision.tool,
            "last_action": decision.tool,
            "tool_call_count": tool_call_count + 1,
            "execution_status": "running",
            "completed_steps": completed_steps,
            "tool_results": tool_results,
            "execution_trace": execution_trace
        }
        return new_state
        
    else:
        # Final Answer Action
        answer = decision.answer or "Task complete."
        execution_trace.append({
            "step": f"planner_{tool_call_count+1}",
            "action": "final",
            "llm_latency_s": llm_latency,
        })
        new_state = {
            "messages": [AIMessage(content=answer)],
            "answer": answer,
            "last_action": "final",
            "execution_status": "completed",
            "completed_steps": completed_steps,
            "tool_results": tool_results,
            "execution_trace": execution_trace
        }
        return new_state
