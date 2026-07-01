"""
Agent Node
==========

The core reasoning node for research queries.

Uses llm.bind_tools() with only web_search and calculator.
Memory and RAG retrieval are NOT tools - they're graph nodes.
"""

from langchain_core.messages import HumanMessage, AIMessage

from llm import llm

AGENT_SYSTEM_PROMPT = """You are an intelligent AI assistant capable of reasoning and using tools when necessary.

Your objective is to answer the user's question accurately, efficiently, and with the minimum number of tool calls required.

GUIDELINES:

1. First understand the user's request.

2. Determine whether a tool is actually required.

3. If no tool is required, immediately provide your Final Answer.

4. Use tools only when they provide information that is missing, external, or computational.

5. Use the minimum number of tool calls necessary.

6. After receiving a tool result, evaluate whether the information is sufficient to answer the question.

7. If insufficient, you MAY perform another tool call with a better query.

8. Never invent tool outputs.

9. Never claim to have searched, calculated, or retrieved something unless the tool was actually used.

CRITICAL INSTRUCTION FOR TOOL CALLING:
Do NOT manually type out tool calls using XML tags like `<function=...>` or `<function\web_search...>`. You must use the official built-in JSON tool calling capability of your API. Just trigger the tool via the API natively. Do not output raw text containing function names.

DECISION PROCESS:

- For questions about company docs, policies, or internal data → NO tool needed (already retrieved above)
- For questions about user's personal info → NO tool needed (already retrieved above)
- For current external information → web_search
- For math/calculations → calculator
- For everything else → reason without tools

STRICT RESPONSE RULES:
1. When answering based on RETRIEVED CONTEXT, do NOT hallucinate definitions or explain concepts (e.g. do not explain what "MERN stack" is unless asked).
2. NEVER add conversational filler or apologies (e.g., "Unfortunately I don't have more details", "If you'd like to share more..."). 
3. If the context is brief, your answer MUST be brief. Just state the facts.
"""


def agent_node(state: dict) -> dict:
    """
    Main reasoning node. Decides when to use tools and generates answer.
    
    Uses streaming agentic loop:
    1. Invoke LLM with bound tools
    2. If tool is called, return tool_calls
    3. If no tool is called, return final answer
    
    Args:
        state: AgentState with question, context fields, and messages
    
    Returns:
        Updated state with messages and potentially answer
    """
    from .tools import tools
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    
    question = state.get("question", "")
    messages = state.get("messages", [])
    context = state.get("_combined_context", "")
    
    system_prompt = AGENT_SYSTEM_PROMPT
    if context:
        system_prompt += f"\n\nRETRIEVED CONTEXT:\n{context}"
        
    llm_input = [SystemMessage(content=system_prompt)]
    llm_input.extend(messages)
    
    # Check if the current question is already the last HumanMessage
    has_current_question = False
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == question:
        has_current_question = True
    elif len(messages) >= 2 and isinstance(messages[-2], HumanMessage) and messages[-2].content == question:
        has_current_question = True
        
    if not has_current_question:
        llm_input.append(HumanMessage(content=question))
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(tools)
    
    # Invoke LLM
    response = llm_with_tools.invoke(llm_input)
    
    new_msgs = []
    if not has_current_question:
        new_msgs.append(HumanMessage(content=question))
    new_msgs.append(response)
    
    # Check if we have tool calls
    if hasattr(response, 'tool_calls') and response.tool_calls:
        print(f"  [Agent] Calling {len(response.tool_calls)} tool(s)")
        return {"messages": new_msgs}
    else:
        # No tool calls, this is the final answer
        answer = response.content
        print(f"  [Agent] Generated answer: {answer[:60]}...")
        return {
            "messages": new_msgs,
            "answer": answer,
        }
