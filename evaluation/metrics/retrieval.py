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
    
    # We check if *any* expected source is in the top K
    # (Since there's usually just 1 expected source chunk in our simple dataset)
    
    expected_set = set(expected_sources)
    
    top_1 = retrieved_chunks[:1]
    top_3 = retrieved_chunks[:3]
    top_5 = retrieved_chunks[:5]
    top_10 = retrieved_chunks[:10]
    
    if expected_set.intersection(top_1):
        metrics["recall_at_1"] = 1.0
    if expected_set.intersection(top_3):
        metrics["recall_at_3"] = 1.0
    if expected_set.intersection(top_5):
        metrics["recall_at_5"] = 1.0
    if expected_set.intersection(top_10):
        metrics["recall_at_10"] = 1.0
        
    for idx, chunk_id in enumerate(retrieved_chunks):
        if chunk_id in expected_set:
            metrics["mrr"] = 1.0 / (idx + 1)
            break
            
    return metrics
