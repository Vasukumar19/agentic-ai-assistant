"""
LangGraph Agent - Main Entry Point
===================================

Multi-Tool Agent using LangGraph workflow orchestration.

Flow:
- Intent Router: Classifies question into chat / memory_update / research_query
- Chat: Direct LLM response (greetings, small talk)
- Memory Update: Extract and save user info
- Research Query: Retrieve context + agent reasoning + tool use

Architecture:
- LLM: Groq (llama-3.3-70b-versatile)
- Tools: web_search, calculator (memory/RAG are nodes, not tools)
- Storage: memory.json, semantic_memory FAISS, faiss_index, chat_history.json
- Embeddings: HuggingFace all-MiniLM-L6-v2 (local)
"""

import json
import os
import logging
from dotenv import load_dotenv
from graph import create_runnable_graph
from state import AgentState
from config import CHAT_HISTORY_PATH, MODEL_NAME
from langchain_core.messages import HumanMessage, AIMessage

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
for noisy_logger in ("httpx", "httpcore", "duckduckgo_search", "urllib3", "primp"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

# Load environment
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY not found. Please add it to your .env file.\n"
        "Get a free key at: https://console.groq.com"
    )

# Build the graph
logger.info("Initializing LangGraph workflow (model: %s)...", MODEL_NAME)
graph = create_runnable_graph()
logger.info("Graph compiled and ready.")


def load_chat_history() -> list:
    """Load persisted chat history into LangChain message objects."""
    history_path = CHAT_HISTORY_PATH
    if not history_path.exists():
        return []

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        return []

    messages = []
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def ask(question: str) -> str:
    """
    Run the agent with a question.

    Args:
        question: User's question or message

    Returns:
        Agent's response
    """
    initial_state: AgentState = {
        "question": question,
        "route": "",
        "retrieval_plan": {"profile": False, "semantic": False, "rag": False},
        "profile_context": "",
        "semantic_context": "",
        "rag_context": "",
        "extracted_profile": {},
        "extracted_semantic": [],
        "answer": "",
        "_combined_context": "",
        "messages": load_chat_history(),
    }

    try:
        result = graph.invoke(initial_state)
        answer = result.get("answer") or "I wasn't able to complete the request after several tool attempts."
    except Exception as e:
        logger.error("Unhandled error while processing question: %s", e, exc_info=True)
        answer = "I encountered an error processing your request. Please try again."

    return answer


def main():
    """Interactive CLI."""
    print("LangGraph Multi-Tool Agent")
    print("Tools: web_search, calculator")
    print("Features: Intent routing, Memory storage, RAG retrieval")
    print("Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            answer = ask(user_input)
            print(f"\n{answer}\n")

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(ask(question))
    else:
        main()