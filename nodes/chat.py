"""
Chat Node
=========

For simple conversations (greetings, small talk).
Invokes LLM directly without tools.
"""

import logging
from llm import llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


def chat_node(state: dict) -> dict:
    """
    Simple chat response without tools or retrieval.

    Args:
        state: AgentState with 'question' field

    Returns:
        Updated state with 'answer' field
    """
    question = state.get("question", "")
    messages = state.get("messages", [])

    system_prompt = "You are a friendly and helpful AI assistant."

    llm_input = [SystemMessage(content=system_prompt)]
    llm_input.extend(messages)

    # Ensure current question is in the input
    has_current_question = False
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == question:
        has_current_question = True

    if not has_current_question:
        llm_input.append(HumanMessage(content=question))

    # Direct LLM invocation for simple chat with history
    response = llm.invoke(llm_input)
    answer = response.content

    logger.debug("Chat response for: %s...", question[:50])

    return {
        "answer": answer,
    }