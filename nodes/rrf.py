def reciprocal_rank_fusion(faiss_results, bm25_results, k=60):
    """
    Implements standard RRF: RRF(d) = sum(1 / (k + rank(d)))
    
    faiss_results: list of (doc, score) where score is distance (lower is better) or None if no score.
                   Wait, we will pass dicts or docs.
    Let's standardise the input: lists of `doc` objects.
    Wait, FAISS returns `(doc, score)`, bm25 returns `doc`.
    We will just accept lists of docs (already ranked).
    """
    
    doc_scores = {}
    doc_map = {}
    
    # Process FAISS
    for rank, doc in enumerate(faiss_results):
        chunk_id = doc.metadata["chunk_id"]
        doc_map[chunk_id] = doc
        if chunk_id not in doc_scores:
            doc_scores[chunk_id] = 0.0
        doc_scores[chunk_id] += 1.0 / (k + rank + 1)
        
    # Process BM25
    for rank, doc in enumerate(bm25_results):
        chunk_id = doc.metadata["chunk_id"]
        doc_map[chunk_id] = doc
        if chunk_id not in doc_scores:
            doc_scores[chunk_id] = 0.0
        doc_scores[chunk_id] += 1.0 / (k + rank + 1)
        
    # Sort by RRF score descending
    sorted_docs = sorted(
        doc_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    return [
        {
            "doc": doc_map[chunk_id],
            "score": score,
            "retriever": "rrf"
        }
        for chunk_id, score in sorted_docs
    ]
