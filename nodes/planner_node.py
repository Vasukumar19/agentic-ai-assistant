import json
import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from llm import llm
from .tools import tools
from config import MAX_TOOL_STEPS

logger = logging.getLogger(__name__)

# Build a list of valid tool names and their schemas for the prompt
TOOL_INFO = "\n".join([f"- {t.name}: {t.description}\n  Schema: {t.args_schema.schema() if t.args_schema else 'None'}" for t in tools])
VALID_TOOL_NAMES = [t.name for t in tools]

class PlannerDecision(BaseModel):
    action: Literal["tool", "final"] = Field(description="Choose 'tool' to call a tool, or 'final' to provide the final answer.")
    tool: Optional[str] = Field(default=None, description=f"If action is 'tool', provide the exact name of the tool to call. Valid options: {VALID_TOOL_NAMES}")
    arguments: Optional[dict] = Field(default=None, description="If action is 'tool', provide a JSON object of arguments matching the tool's schema.")
    answer: Optional[str] = Field(default=None, description="If action is 'final', provide the final response to the user.")

PLANNER_SYSTEM_PROMPT = f"""You are a multi-step execution planner. 
Your job is to analyze the user's query, any retrieved context, and previous tool execution results, then decide the SINGLE next action.

Available Tools:
{TOOL_INFO}

Rules:
1. You may only choose 'tool' or 'final'.
2. If you choose 'tool', you MUST provide a valid tool name and perfectly formatted JSON arguments.
3. If you do not have enough information to answer the question, you MUST choose 'tool' to gather more information.
4. If you have gathered all necessary information, choose 'final' and construct the final answer.
5. Do NOT hallucinate tool names. Only use the tools provided above.
"""

def planner_node(state: dict) -> dict:
    question = state.get("question", "")
    context = state.get("_combined_context", "")
    messages = state.get("messages", [])
    
    # Initialize execution state variables if they don't exist
    tool_call_count = state.get("tool_call_count", 0)
    completed_steps = state.get("completed_steps", [])
    tool_results = state.get("tool_results", [])
    
    if context:
        user_prompt = f"RETRIEVED CONTEXT:\n{context}\n\nUser Query: {question}"
    else:
        user_prompt = f"User Query: {question}"
        
    # Summarize tool history for the planner
    # First, let's update tool_results if the last message was a ToolMessage
    if messages and messages[-1].type == "tool":
        last_tool_msg = messages[-1]
        # Find the matching tool call in the previous AIMessage
        if len(messages) >= 2 and messages[-2].type == "ai":
            last_ai_msg = messages[-2]
            if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
                # Assuming 1 tool call per step in our new planner
                call = last_ai_msg.tool_calls[0]
                tool_name = call["name"]
                tool_args = call["args"]
                
                # We only append if this is a new result (by checking counts)
                if len(tool_results) < tool_call_count:
                    completed_steps.append(tool_name)
                    tool_results.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": last_tool_msg.content
                    })

    if tool_results:
        history_str = "PREVIOUS TOOL EXECUTIONS:\n"
        for i, step in enumerate(completed_steps):
            history_str += f"\nStep {i+1}: Called '{step}'\n"
            if i < len(tool_results):
                res = tool_results[i]
                history_str += f"Arguments: {json.dumps(res.get('arguments', {}))}\n"
                history_str += f"Result: {res.get('result', 'Error/No Result')}\n"
        user_prompt = f"{history_str}\n\n{user_prompt}"

    structured_llm = llm.with_structured_output(PlannerDecision)
    
    try:
        decision = structured_llm.invoke([
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ])
    except Exception as e:
        logger.error(f"Planner failed to generate structured output: {e}")
        # Fallback to final answer if planner crashes
        return {
            "answer": "I'm sorry, I encountered an internal error while planning the next step.",
            "execution_status": "error"
        }
        
    if decision.action == "tool":
        if decision.tool not in VALID_TOOL_NAMES:
            logger.warning(f"Planner hallucinated tool: {decision.tool}")
            return {
                "answer": f"I tried to use an invalid tool: {decision.tool}. I cannot complete the request.",
                "execution_status": "error"
            }
            
        tool_call_id = f"call_{tool_call_count}"
        tool_call = {
            "name": decision.tool,
            "args": decision.arguments or {},
            "id": tool_call_id
        }
        
        # We append an AIMessage with the tool_call to satisfy LangGraph's ToolNode
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        
        new_state = {
            "messages": [ai_msg],
            "current_step": decision.tool,
            "tool_call_count": tool_call_count + 1,
            "execution_status": "running",
            "completed_steps": completed_steps,
            "tool_results": tool_results
        }
        return new_state
        
    else:
        # Final answer
        answer = decision.answer or "Task complete."
        new_state = {
            "messages": [AIMessage(content=answer)],
            "answer": answer,
            "execution_status": "completed",
            "completed_steps": completed_steps,
            "tool_results": tool_results
        }
        return new_state
