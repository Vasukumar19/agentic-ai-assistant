"""
Memory Retriever Node
=====================

Fetches user's stored information:
- Profile memory from memory.json
- Semantic memory from FAISS index

Formats as readable text for LLM consumption.
"""

import json
import logging
from langchain_community.vectorstores import FAISS
from config import MEMORY_FILE, SEMANTIC_MEMORY_DIR
from .embeddings import embeddings

logger = logging.getLogger(__name__)


def memory_retriever_node(state: dict) -> dict:
    """
    Retrieve user's profile and semantic memory.
    
    Args:
        state: AgentState with 'retrieval_plan' and 'question' fields
    
    Returns:
        Updated state with 'profile_context' and 'semantic_context' fields
    """
    retrieval_plan = state.get("retrieval_plan", {})
    question = state.get("question", "")
    
    profile_context = ""
    semantic_context = ""
    
    # Retrieve profile memory
    if retrieval_plan.get("profile", False):
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    memory = json.load(f)
                
                # Format as readable text
                if memory:
                    lines = ["=== PROFILE INFORMATION ==="]
                    
                    if "name" in memory:
                        lines.append(f"Name: {memory['name']}")
                    if "goal" in memory:
                        lines.append(f"Goal: {memory['goal']}")
                    if "profession" in memory:
                        lines.append(f"Profession: {memory['profession']}")
                    if "education" in memory:
                        lines.append(f"Education: {memory['education']}")
                    if "interests" in memory and memory["interests"]:
                        interests = memory["interests"]
                        if isinstance(interests, list):
                            interests = ", ".join(interests)
                        lines.append(f"Interests: {interests}")
                    if "favorite_technologies" in memory and memory["favorite_technologies"]:
                        techs = memory["favorite_technologies"]
                        if isinstance(techs, list):
                            techs = ", ".join(techs)
                        lines.append(f"Favorite Technologies: {techs}")
                    if "preferences" in memory and memory["preferences"]:
                        prefs = memory["preferences"]
                        if isinstance(prefs, list):
                            prefs = ", ".join(prefs)
                        lines.append(f"Preferences: {prefs}")
                    
                    profile_context = "\n".join(lines)
                    print(f"  [Memory Retriever] Fetched profile memory ({len(memory)} fields)")
            except json.JSONDecodeError as e:
                logger.warning(f"[Memory Retriever] Profile JSON parse failed: {e}")
    
    # Retrieve semantic memory
    if retrieval_plan.get("semantic", False):
        if SEMANTIC_MEMORY_DIR.exists():
            try:
                vector_store = FAISS.load_local(
                    str(SEMANTIC_MEMORY_DIR),
                    embeddings,
                    allow_dangerous_deserialization=True
                )
                
                # Search for relevant memories
                results = vector_store.similarity_search(question, k=3)
                
                if results:
                    lines = ["=== SEMANTIC MEMORIES ==="]
                    for i, doc in enumerate(results, 1):
                        lines.append(f"{i}. {doc.page_content}")
                    
                    semantic_context = "\n".join(lines)
                    print(f"  [Memory Retriever] Fetched {len(results)} semantic memories")
                else:
                    print(f"  [Memory Retriever] No relevant semantic memories found")
            except Exception as e:
                logger.warning(f"[Memory Retriever] Error loading semantic memory FAISS index: {e}")
    
    return {
        "profile_context": profile_context,
        "semantic_context": semantic_context,
    }
