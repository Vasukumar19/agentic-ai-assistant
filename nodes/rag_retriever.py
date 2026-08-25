"""
RAG Retriever Node — with observability, timeout, retrieval metadata.
"""

import logging
import time
from pathlib import Path
from langchain_community.vectorstores import FAISS
from config import FAISS_INDEX_DIR, RETRIEVAL_MODE, RRF_K, TIMEOUT_RETRIEVAL_S
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
    t0 = time.perf_counter()
    retrieval_plan = state.get("retrieval_plan", {})

    if not retrieval_plan.get("rag", False):
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            add_latency(state, "rag_retriever", dur)
            ev = make_event(state, "RETRIEVAL", "rag_retriever", duration_ms=dur, status="success",
                            metadata={"retrieval_mode": RETRIEVAL_MODE, "skipped": True, "reason": "plan rag=false"})
            append_event(state, ev)
        except Exception:
            pass
        return {"rag_context": "", "retrieved_chunks": [], "retrieval_metrics": {},
                "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                "latency_breakdown": state.get("latency_breakdown")}

    vectorstore = _get_vectorstore()
    if vectorstore is None:
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            from observability.errors import make_error_payload, ErrorType
            add_latency(state, "rag_retriever", dur)
            err = make_error_payload(ErrorType.RETRIEVAL_ERROR.value, "rag_retriever",
                                     "FAISS index not available", trace_id=state.get("trace_id"))
            ev = make_event(state, "RETRIEVAL", "rag_retriever", duration_ms=dur, status="error",
                            metadata={"retrieval_mode": RETRIEVAL_MODE}, error=err)
            append_event(state, ev)
        except Exception:
            pass
        return {"rag_context": "", "retrieved_chunks": [], "retrieval_metrics": {},
                "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                "latency_breakdown": state.get("latency_breakdown")}

    question = state.get("question", "")
    search_query = question.strip()

    rag_context = ""
    candidate_items = []
    
    t_retrieval_start = time.perf_counter()
    rerank_lat = 0
    retrieval_meta = {"retrieval_mode": RETRIEVAL_MODE}
    
    try:
        def _do_retrieval():
            nonlocal candidate_items, rerank_lat
            if RETRIEVAL_MODE == "faiss":
                results = vectorstore.similarity_search_with_score(search_query, k=5)
                for doc, score in results:
                    if score <= SIMILARITY_THRESHOLD:
                        candidate_items.append({"doc": doc, "score": score, "retriever": "faiss"})
                retrieval_meta["faiss_candidates"] = len(results)
            elif RETRIEVAL_MODE == "hybrid":
                results = vectorstore.similarity_search_with_score(search_query, k=5)
                bm25_results = bm25_search(search_query, k=5)
                merged = {}
                for doc, score in results:
                    if score <= SIMILARITY_THRESHOLD:
                        merged[doc.metadata["chunk_id"]] = {"doc": doc, "score": score, "retriever": "faiss"}
                for doc in bm25_results:
                    merged.setdefault(doc.metadata["chunk_id"], {"doc": doc, "score": None, "retriever": "bm25"})
                candidate_items = list(merged.values())
                retrieval_meta.update({"faiss_candidates": len(results), "bm25_candidates": len(bm25_results),
                                       "merged_candidates": len(candidate_items)})
            elif RETRIEVAL_MODE == "rrf":
                faiss_results = vectorstore.similarity_search_with_score(search_query, k=20)
                faiss_docs = [doc for doc, score in faiss_results]
                bm25_results = bm25_search(search_query, k=20)
                candidate_items = reciprocal_rank_fusion(faiss_docs, bm25_results, k=RRF_K)[:5]
                retrieval_meta.update({"faiss_candidates": len(faiss_docs), "bm25_candidates": len(bm25_results),
                                       "rrf_candidates": len(candidate_items)})
            elif RETRIEVAL_MODE == "reranker":
                faiss_results = vectorstore.similarity_search_with_score(search_query, k=20)
                faiss_docs = [doc for doc, score in faiss_results]
                bm25_results = bm25_search(search_query, k=20)
                fused_items = reciprocal_rank_fusion(faiss_docs, bm25_results, k=RRF_K)
                t_rerank_start = time.perf_counter()
                candidate_items = rerank(search_query, fused_items, top_k=5)
                rerank_lat = time.perf_counter() - t_rerank_start
                retrieval_meta.update({"faiss_candidates": len(faiss_docs), "bm25_candidates": len(bm25_results),
                                       "reranked_candidates": len(candidate_items), "reranker_latency_ms": int(rerank_lat*1000)})

        # timeout wrapper
        from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
        try:
            run_with_timeout(_do_retrieval, TIMEOUT_RETRIEVAL_S)
        except ObsTimeout as te:
            from observability.errors import make_error_payload, ErrorType
            from observability.trace import make_event, append_event, add_latency
            dur = int((time.perf_counter() - t0) * 1000)
            add_latency(state, "rag_retriever", dur)
            err = make_error_payload(ErrorType.TIMEOUT_ERROR.value, "rag_retriever", str(te), trace_id=state.get("trace_id"))
            ev = make_event(state, "TIMEOUT", "rag_retriever", duration_ms=dur, status="timeout",
                            metadata={"timeout_s": TIMEOUT_RETRIEVAL_S}, error=err)
            append_event(state, ev)
            # also emit RETRIEVAL error
            ev2 = make_event(state, "RETRIEVAL", "rag_retriever", duration_ms=dur, status="error",
                             metadata={"retrieval_mode": RETRIEVAL_MODE, "timeout": True}, error=err)
            append_event(state, ev2)
            return {"rag_context": "", "retrieved_chunks": [], "retrieval_metrics": {},
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}

        t_retrieval_end = time.perf_counter()

        lines = ["=== COMPANY DOCUMENTS ==="]
        retrieved_chunks = []
        doc_infos = []
        for i, item in enumerate(candidate_items, 1):
            doc = item["doc"]
            score = item["score"]
            retriever = item["retriever"]
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "")
            chunk_id = doc.metadata.get("chunk_id", -1)
            retrieved_chunks.append(chunk_id)
            doc_infos.append({"chunk_id": chunk_id, "source": Path(source).name, "page": page,
                              "retriever": retriever, "score": score, "rank": i})
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
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            add_latency(state, "rag_retriever", dur)
            retrieval_meta.update({"retrieved_chunks": len(retrieved_chunks), "rag_context_chars": len(rag_context),
                                   "retrieval_latency_ms": int(metrics["retrieval_latency"]*1000),
                                   "reranker_latency_ms": int(metrics["reranker_latency"]*1000),
                                   "document_ids": doc_infos})
            ev = make_event(state, "RETRIEVAL", "rag_retriever", duration_ms=dur, status="success",
                            metadata=retrieval_meta)
            append_event(state, ev)
            # query rewrite trace (even though currently disabled)
            ev_qr = make_event(state, "QUERY_REWRITE", "rag_retriever", duration_ms=0, status="success",
                               metadata={"original": question[:200], "rewritten": search_query[:200]})
            append_event(state, ev_qr)
        except Exception:
            pass

        return {
            "rag_context": rag_context,
            "retrieved_chunks": retrieved_chunks,
            "retrieval_metrics": metrics,
            "trace_events": state.get("trace_events"),
            "trace_step": state.get("trace_step"),
            "latency_breakdown": state.get("latency_breakdown"),
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("RAG retrieval error: %s", e, exc_info=True)
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            from observability.errors import classify_error, make_error_payload
            add_latency(state, "rag_retriever", dur)
            err_type = classify_error(e, component="rag_retriever")
            err = make_error_payload(err_type, "rag_retriever", str(e), trace_id=state.get("trace_id"))
            ev = make_event(state, "RETRIEVAL", "rag_retriever", duration_ms=dur, status="error",
                            metadata={"error": str(e)[:300]}, error=err)
            append_event(state, ev)
        except Exception:
            pass
        return {"rag_context": "", "retrieved_chunks": [], "retrieval_metrics": {},
                "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                "latency_breakdown": state.get("latency_breakdown")}

