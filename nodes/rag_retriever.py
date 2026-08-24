"""
RAG Retriever Node
==================

Searches through company documents (PDF/TXT) using FAISS semantic search.
Formats results for LLM consumption.
"""

import logging
import time
from pathlib import Path
from langchain_community.vectorstores import FAISS
from config import FAISS_INDEX_DIR, RETRIEVAL_MODE, RRF_K
from .embeddings import embeddings
from langchain_core.prompts import ChatPromptTemplate
from llm import llm
from .bm25 import bm25_search
from reranker import rerank
from .rrf import reciprocal_rank_fusion

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

_vectorstore = None
_vectorstore_load_failed = False

def _get_vectorstore():
    global _vectorstore, _vectorstore_load_failed

    if _vectorstore is not None:
        return _vectorstore

    if _vectorstore_load_failed:
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
    retrieval_plan = state.get("retrieval_plan", {})

    if not retrieval_plan.get("rag", False):
        return {"rag_context": "", "retrieved_chunks": [], "retrieval_metrics": {}}

    vectorstore = _get_vectorstore()
    if vectorstore is None:
        return {"rag_context": "", "retrieved_chunks": [], "retrieval_metrics": {}}

    question = state.get("question", "")
    search_query = question.strip()

    rag_context = ""
    candidate_items = []
    
    t0 = time.time()
    t_retrieval_start = time.time()
    rerank_lat = 0
    
    try:
        if RETRIEVAL_MODE == "faiss":
            results = vectorstore.similarity_search_with_score(search_query, k=5)
            for doc, score in results:
                if score <= SIMILARITY_THRESHOLD:
                    candidate_items.append({
                        "doc": doc,
                        "score": score,
                        "retriever": "faiss"
                    })
        elif RETRIEVAL_MODE == "hybrid":
            results = vectorstore.similarity_search_with_score(search_query, k=5)
            bm25_results = bm25_search(search_query, k=5)
            merged = {}
            for doc, score in results:
                if score <= SIMILARITY_THRESHOLD:
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
            candidate_items = list(merged.values())
        elif RETRIEVAL_MODE == "rrf":
            faiss_results = vectorstore.similarity_search_with_score(search_query, k=20)
            faiss_docs = [doc for doc, score in faiss_results] # Ignore threshold for RRF
            bm25_results = bm25_search(search_query, k=20)
            candidate_items = reciprocal_rank_fusion(faiss_docs, bm25_results, k=RRF_K)[:5]
        elif RETRIEVAL_MODE == "reranker":
            faiss_results = vectorstore.similarity_search_with_score(search_query, k=20)
            faiss_docs = [doc for doc, score in faiss_results]
            bm25_results = bm25_search(search_query, k=20)
            fused_items = reciprocal_rank_fusion(faiss_docs, bm25_results, k=RRF_K)
            
            t_rerank_start = time.time()
            candidate_items = rerank(search_query, fused_items, top_k=5)
            t_rerank_end = time.time()
            rerank_lat = t_rerank_end - t_rerank_start
        else:
            rerank_lat = 0
            
        t_retrieval_end = time.time()

        lines = ["=== COMPANY DOCUMENTS ==="]
        retrieved_chunks = []

        for i, item in enumerate(candidate_items, 1):
            doc = item["doc"]
            score = item["score"]
            retriever = item["retriever"]

            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "")
            chunk_id = doc.metadata.get("chunk_id", -1)
            retrieved_chunks.append(chunk_id)

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
            lines.append("")

        rag_context = "\n".join(lines)
        
        metrics = {
            "retrieval_latency": t_retrieval_end - t_retrieval_start - rerank_lat,
            "reranker_latency": rerank_lat
        }

    except Exception as e:
        logger.error("RAG retrieval error: %s", e, exc_info=True)
        metrics = {}

    return {
        "rag_context": rag_context,
        "retrieved_chunks": retrieved_chunks if 'retrieved_chunks' in locals() else [],
        "retrieval_metrics": metrics if 'metrics' in locals() else {}
    }