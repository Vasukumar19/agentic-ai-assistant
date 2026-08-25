def evaluate_retrieval(expected_sources, retrieved_chunks):
    if not expected_sources:
        return None
        
    metrics = {
        "recall_at_1": 0.0,
        "recall_at_3": 0.0,
        "recall_at_5": 0.0,
        "recall_at_10": 0.0,
        "mrr": 0.0
    }
    

    # Since chunk_ids are in format 'docname_chunk_XXX', we can match the prefix
    # or just match the exact document name if expected_sources stores document names.
    # Let's extract the document name from the retrieved chunk IDs.
    retrieved_docs = []
    for c in retrieved_chunks:
        if isinstance(c, str) and "_chunk_" in c:
            retrieved_docs.append(c.split("_chunk_")[0])
        else:
            retrieved_docs.append(str(c))
            
    # expected_sources contains the expected document names (e.g. 'hr_policy')
    expected_docs = [str(e).split("_chunk_")[0] if isinstance(e, str) and "_chunk_" in e else str(e) for e in expected_sources]

    # Calculate Recalls
    for k in [1, 3, 5, 10]:
        k_docs = retrieved_docs[:k]
        if any(d in k_docs for d in expected_docs):
            metrics[f"recall_at_{k}"] = 1.0
        
    for idx, doc_id in enumerate(retrieved_docs):
        if doc_id in expected_docs:
            metrics["mrr"] = 1.0 / (idx + 1)
            break
            
    return metrics
