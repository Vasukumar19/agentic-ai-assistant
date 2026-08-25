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
    """
    import time
    t0 = time.perf_counter()
    retrieval_plan = state.get("retrieval_plan", {})
    question = state.get("question", "")

    profile_context = ""
    semantic_context = ""
    mem_read_meta = {"profile_requested": bool(retrieval_plan.get("profile", False)),
                     "semantic_requested": bool(retrieval_plan.get("semantic", False))}

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
                    logger.info("Fetched profile memory (%d fields)", len(memory))
            except json.JSONDecodeError as e:
                logger.warning("Profile JSON parse failed: %s", e)

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
                    logger.info("Fetched %d semantic memories", len(results))
                else:
                    logger.debug("No relevant semantic memories found")
            except Exception as e:
                logger.warning("Error loading semantic memory FAISS index: %s", e)

    dur = int((time.perf_counter() - t0) * 1000)
    try:
        from observability.trace import make_event, append_event, add_latency
        add_latency(state, "memory_retriever", dur)
        meta = dict(mem_read_meta)
        meta.update({"profile_chars": len(profile_context), "semantic_chars": len(semantic_context),
                     "duration_ms": dur, "operation": "read"})
        ev = make_event(state, "MEMORY_READ", "memory_retriever", duration_ms=dur, status="success", metadata=meta)
        append_event(state, ev)
        # also emit generic RETRIEVAL event for the unified view
        ev2 = make_event(state, "RETRIEVAL", "memory_retriever", duration_ms=dur, status="success",
                         metadata={"type": "memory", "profile": bool(profile_context), "semantic": bool(semantic_context)})
        append_event(state, ev2)
    except Exception:
        pass
    return {
        "profile_context": profile_context,
        "semantic_context": semantic_context,
        "trace_events": state.get("trace_events"),
        "trace_step": state.get("trace_step"),
        "latency_breakdown": state.get("latency_breakdown"),
    }