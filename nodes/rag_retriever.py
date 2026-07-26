"""
RAG Retriever Node
==================

Searches through company documents (PDF/TXT) using FAISS semantic search.
Formats results for LLM consumption.
"""

import logging
from pathlib import Path
from langchain_community.vectorstores import FAISS
from config import FAISS_INDEX_DIR
from .embeddings import embeddings
from langchain_core.prompts import ChatPromptTemplate
from llm import llm
from .bm25 import bm25_search
from reranker import rerank

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.8


rewrite_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
    Rewrite the user's question into a concise search query.

    Rules:
    - Keep the meaning.
    - Expand synonyms.
    - Remove unnecessary words.
    - Return ONLY the rewritten query.
    """
        ),
        ("human", "{question}")
    ])
chain = rewrite_prompt | llm

# Vectorstore is lazily loaded and cached on first use (see _get_vectorstore()).
# Loading it at import time would crash the whole app on startup if the index
# is missing or corrupted, instead of letting rag_retriever_node degrade
# gracefully to "no RAG context available" for that turn.
_vectorstore = None
_vectorstore_load_failed = False


def _get_vectorstore():
    """
    Lazily load and cache the FAISS vectorstore. Returns None if the index
    doesn't exist or fails to load, so the caller can degrade gracefully
    instead of crashing.
    """
    global _vectorstore, _vectorstore_load_failed

    if _vectorstore is not None:
        return _vectorstore

    if _vectorstore_load_failed:
        # Already tried and failed this run; don't keep retrying every call.
        return None

    if not FAISS_INDEX_DIR.exists():
        logger.warning("FAISS index directory not found at %s (index not built)", FAISS_INDEX_DIR)
        _vectorstore_load_failed = True
        return None

    try:
        _vectorstore = FAISS.load_local(
            str(FAISS_INDEX_DIR),
            embeddings,
            allow_dangerous_deserialization=True
        )
        return _vectorstore
    except Exception as e:
        logger.error("Failed to load FAISS index from %s: %s", FAISS_INDEX_DIR, e, exc_info=True)
        _vectorstore_load_failed = True
        return None


def rag_retriever_node(state: dict) -> dict:
    """
    Retrieve relevant documents from FAISS index.

    Args:
        state: AgentState with 'retrieval_plan' and 'question' fields

    Returns:
        Updated state with 'rag_context' field
    """
    retrieval_plan = state.get("retrieval_plan", {})

    if not retrieval_plan.get("rag", False):
        return {"rag_context": ""}

    vectorstore = _get_vectorstore()
    if vectorstore is None:
        # Index missing or failed to load — degrade gracefully, don't crash the graph.
        return {"rag_context": ""}

    question = state.get("question", "")
    search_query = chain.invoke({"question": question}).content.strip()

    rag_context = ""

    try:
        # Search for relevant documents
        results = vectorstore.similarity_search_with_score(search_query, k=20)
        bm25_results = bm25_search(search_query, k=20)
        merged = {}
        for doc, score in results:
            merged[doc.metadata["chunk_id"]] = {
                "doc": doc,
                "score": score,
                "retriever": "faiss",
            }

        for doc in bm25_results:
            merged.setdefault(
                doc.metadata["chunk_id"],
                {
                    "doc": doc,
                    "score": None,
                    "retriever": "bm25",
                },
            )

        if not results:
            logger.debug("No relevant documents found")
            return {"rag_context": ""}
            # tune later

        filtered = []

        for item in merged.values():
            if item["retriever"] == "bm25":
                filtered.append(item)
            elif item["score"] <= SIMILARITY_THRESHOLD:
                filtered.append(item)

        if not filtered:
            logger.debug("No documents passed filtering")
            return {"rag_context": ""}

        filtered.sort(
            key=lambda x: (
                x["score"] is None,
                x["score"] if x["score"] is not None else float("inf")
            )
        )

        candidate_items = rerank(
            search_query,
            filtered[:20],
            top_k=5,
        )

        # Format results
        lines = ["=== COMPANY DOCUMENTS ==="]

        for i, item in enumerate(candidate_items, 1):
            doc = item["doc"]
            score = item["score"]
            retriever = item["retriever"]

            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "")

            # Format document reference
            label = f"[Doc {i} | {Path(source).name}"
            if page != "":
                label += f" p.{page + 1}]"
            else:
                label += "]"
            lines.append(label)
            lines.append(f"Retriever : {retriever}")

            if score is not None:
                lines.append(f"Score     : {score:.4f}")
            lines.append(doc.page_content.strip())
            lines.append("")  # Blank line between documents

        rag_context = "\n".join(lines)

    except Exception as e:
        logger.error("RAG retrieval error: %s", e, exc_info=True)

    return {"rag_context": rag_context}