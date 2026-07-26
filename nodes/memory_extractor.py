"""
Memory Extraction & Storage Nodes
==================================

memory_extractor_node: Extract profile and semantic memory from user message
memory_saver_node: Save extracted data to disk
memory_response_node: Generate confirmation response
"""

import json
import logging
from llm import llm
from config import MEMORY_FILE, SEMANTIC_MEMORY_DIR

logger = logging.getLogger(__name__)

MEMORY_EXTRACTOR_PROMPT = """You are a memory extractor.

Return ONLY valid JSON with no explanation.

Schema:
{
  "extracted_profile": {
    "name": "",
    "goal": "",
    "profession": "",
    "education": "",
    "interests": [],
    "favorite_technologies": [],
    "preferences": []
  },
  "extracted_semantic": []
}

Rules:
- extracted_profile should contain stable personal facts only.
- extracted_semantic should contain long-term memories, projects, courses, or experiences.
- Do not include conversational filler or questions.
- If nothing relevant is found, return empty values.

Message: {message}"""


def memory_extractor_node(state: dict) -> dict:
    """Extract memory facts from the user's message and return structured memory updates."""
    question = state.get("question", "")
    prompt = MEMORY_EXTRACTOR_PROMPT.replace("{message}", question)

    response = llm.invoke(prompt)
    content = response.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    default_profile = {}
    default_semantic = []

    try:
        data = json.loads(content)
        extracted_profile = data.get("extracted_profile", default_profile) or default_profile
        extracted_semantic = data.get("extracted_semantic", default_semantic) or default_semantic
    except json.JSONDecodeError as e:
        logger.warning("Memory extraction JSON parse failed: %s", e)
        extracted_profile = default_profile
        extracted_semantic = default_semantic

    return {
        "extracted_profile": extracted_profile,
        "extracted_semantic": extracted_semantic,
    }


def memory_saver_node(state: dict) -> dict:
    """
    Save extracted memory to disk.
    Updates memory.json with profile data.
    Adds semantic memories to FAISS index.

    Args:
        state: AgentState with 'extracted_profile' and 'extracted_semantic' fields

    Returns:
        Updated state (or None)
    """
    from datetime import datetime
    from langchain_core.documents import Document
    from langchain_community.vectorstores import FAISS
    from .embeddings import embeddings

    extracted_profile = state.get("extracted_profile", {})
    extracted_semantic = state.get("extracted_semantic", [])

    # Save profile memory
    if extracted_profile:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Load existing memory
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    memory = json.load(f)
            except json.JSONDecodeError as e:
                logger.warning("Profile JSON parse failed: %s", e)
                memory = {}
        else:
            memory = {}

        # Update with extracted data
        memory.update(extracted_profile)

        # Save back
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=4)

        logger.info("Saved profile memory")

    # Save semantic memories
    if extracted_semantic:
        SEMANTIC_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if SEMANTIC_MEMORY_DIR.exists():
            try:
                vector_store = FAISS.load_local(
                    str(SEMANTIC_MEMORY_DIR),
                    embeddings,
                    allow_dangerous_deserialization=True
                )
            except Exception as e:
                logger.warning("Error loading semantic memory FAISS index: %s", e)
                vector_store = None
        else:
            vector_store = None

        # Add each semantic memory
        for memory_text in extracted_semantic:
            doc = Document(
                page_content=memory_text,
                metadata={"timestamp": datetime.utcnow().isoformat()}
            )

            if vector_store is None:
                vector_store = FAISS.from_documents([doc], embeddings)
            else:
                vector_store.add_documents([doc])

        # Save index
        if vector_store is not None:
            vector_store.save_local(str(SEMANTIC_MEMORY_DIR))
            logger.info("Saved %d semantic memories", len(extracted_semantic))

    return {}


def memory_response_node(state: dict) -> dict:
    """
    Generate a confirmation response for memory update.

    Args:
        state: AgentState with 'extracted_profile' and 'extracted_semantic' fields

    Returns:
        Updated state with 'answer' field
    """
    extracted_profile = state.get("extracted_profile", {})
    extracted_semantic = state.get("extracted_semantic", [])

    # Build confirmation message
    parts = ["Got it! I'll remember that"]

    if "name" in extracted_profile:
        parts.append(f"your name is {extracted_profile['name']}")

    if "goal" in extracted_profile:
        parts.append(f"your goal is to become an {extracted_profile['goal']}")

    if extracted_semantic:
        parts.append(f"you {extracted_semantic[0].lower()}")
        for mem in extracted_semantic[1:]:
            parts.append(f"and you {mem.lower()}")

    answer = ", ".join(parts) + "." if parts else "I've updated my memory."

    logger.debug("Memory update confirmation: %s...", answer[:60])

    return {
        "answer": answer,
    }