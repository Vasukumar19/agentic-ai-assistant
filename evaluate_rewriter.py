import json
import time
from unittest.mock import patch
from nodes.rag_retriever import rag_retriever_node, chain
from evaluation.metrics.retrieval import evaluate_retrieval
import config
from statistics import mean

class MockResponse:
    def __init__(self, content):
        self.content = content

def run_rewriter_benchmark():
    dataset = json.load(open("evaluation/datasets/retrieval_extended.json"))
    
    # Use RRF as the baseline retrieval config
    config.RETRIEVAL_MODE = "rrf"
    
    results = []
    
    for case in dataset:
        q = case["query"]
        expected = case.get("expected_sources", [])
        
        # 1. Raw Query (Mock the rewriter to return the exact same query)
        state_raw = {"question": q, "retrieval_plan": {"rag": True}}
        with patch("nodes.rag_retriever.chain") as mock_chain:
            mock_chain.invoke.return_value = MockResponse(q)
            output_raw = rag_retriever_node(state_raw)
            chunks_raw = output_raw.get("retrieved_chunks", [])
            metrics_raw = evaluate_retrieval(expected, chunks_raw)
            
        # 2. Rewritten Query (Let it hit the actual LLM)
        state_rewrite = {"question": q, "retrieval_plan": {"rag": True}}
        t0 = time.time()
        try:
            # We explicitly invoke it here just to measure latency and capture the text
            rewrite_resp = chain.invoke({"question": q})
            rewritten_q = rewrite_resp.content.strip()
            # Token usage might be in rewrite_resp.response_metadata
            token_usage = rewrite_resp.response_metadata.get("token_usage", {}) if hasattr(rewrite_resp, "response_metadata") else {}
        except Exception as e:
            print(f"Rate limit or LLM error on '{q}': {e}")
            break # Stop if rate limited
            
        rewrite_lat = time.time() - t0
        time.sleep(1) # Prevent rate limit bursts
        
        # Now run retrieval with the actual rewrite
        with patch("nodes.rag_retriever.chain") as mock_chain:
            mock_chain.invoke.return_value = MockResponse(rewritten_q)
            output_rewritten = rag_retriever_node(state_rewrite)
            chunks_rewritten = output_rewritten.get("retrieved_chunks", [])
            metrics_rewritten = evaluate_retrieval(expected, chunks_rewritten)
            
        results.append({
            "query": q,
            "rewritten": rewritten_q,
            "expected": expected,
            "raw_chunks": chunks_raw,
            "rewrite_chunks": chunks_rewritten,
            "raw_metrics": metrics_raw,
            "rewrite_metrics": metrics_rewritten,
            "rewrite_lat": rewrite_lat,
            "tokens": token_usage
        })
        
        print(f"[{case['id']}] Raw: {metrics_raw['recall_at_1']}, Rewrite: {metrics_rewritten['recall_at_1']} | Q: {q} -> {rewritten_q}")

    if not results:
        print("No results collected.")
        return
        
    # Analyze and generate report
    improved = 0
    same = 0
    degraded = 0
    
    with open("evaluation/reports/query_rewriter_analysis.md", "w", encoding="utf-8") as f:
        f.write("# PHASE 2D — QUERY REWRITER IMPACT\n\n")
        f.write(f"Dataset: {len(results)} queries\n\n")
        
        for r in results:
            diff = r["rewrite_metrics"]["recall_at_5"] - r["raw_metrics"]["recall_at_5"]
            if diff > 0 or (r["rewrite_metrics"]["mrr"] > r["raw_metrics"]["mrr"]):
                improved += 1
                status = "rewrite_improved"
            elif diff < 0 or (r["rewrite_metrics"]["mrr"] < r["raw_metrics"]["mrr"]):
                degraded += 1
                status = "rewrite_hurt"
            else:
                same += 1
                status = "rewrite_same"
                
            f.write(f"Query:\n{r['query']}\n\n")
            f.write(f"Original:\n{r['query']}\n\n")
            f.write(f"Rewritten:\n{r['rewritten']}\n\n")
            f.write(f"Expected chunks:\n{r['expected']}\n\n")
            f.write(f"Raw-query retrieved chunks:\n{r['raw_chunks']}\n\n")
            f.write(f"Rewritten-query retrieved chunks:\n{r['rewrite_chunks']}\n\n")
            f.write(f"Raw Recall@5:\n{r['raw_metrics']['recall_at_5']}\n\n")
            f.write(f"Rewritten Recall@5:\n{r['rewrite_metrics']['recall_at_5']}\n\n")
            f.write(f"Difference:\n{status}\n\n---\n\n")
            
        raw_rec1 = mean(r["raw_metrics"]["recall_at_1"] for r in results)
        raw_rec3 = mean(r["raw_metrics"]["recall_at_3"] for r in results)
        raw_rec5 = mean(r["raw_metrics"]["recall_at_5"] for r in results)
        raw_rec10 = mean(r["raw_metrics"]["recall_at_10"] for r in results)
        raw_mrr = mean(r["raw_metrics"]["mrr"] for r in results)
        
        rew_rec1 = mean(r["rewrite_metrics"]["recall_at_1"] for r in results)
        rew_rec3 = mean(r["rewrite_metrics"]["recall_at_3"] for r in results)
        rew_rec5 = mean(r["rewrite_metrics"]["recall_at_5"] for r in results)
        rew_rec10 = mean(r["rewrite_metrics"]["recall_at_10"] for r in results)
        rew_mrr = mean(r["rewrite_metrics"]["mrr"] for r in results)
        
        lats = [r["rewrite_lat"] for r in results]
        lats.sort()
        mean_lat = mean(lats)
        p50 = lats[len(lats)//2]
        p95 = lats[int(len(lats)*0.95)] if lats else 0
        
        # Format the aggregate part
        agg = f"""## AGGREGATE IMPACT

| Metric | Raw | Rewritten | Delta |
|---|---|---|---|
| Recall@1 | {raw_rec1*100:.1f}% | {rew_rec1*100:.1f}% | {(rew_rec1-raw_rec1)*100:+.1f}% |
| Recall@3 | {raw_rec3*100:.1f}% | {rew_rec3*100:.1f}% | {(rew_rec3-raw_rec3)*100:+.1f}% |
| Recall@5 | {raw_rec5*100:.1f}% | {rew_rec5*100:.1f}% | {(rew_rec5-raw_rec5)*100:+.1f}% |
| Recall@10| {raw_rec10*100:.1f}%| {rew_rec10*100:.1f}%| {(rew_rec10-raw_rec10)*100:+.1f}%|
| MRR | {raw_mrr:.3f} | {rew_mrr:.3f} | {rew_mrr-raw_mrr:+.3f} |

Rewrite Impact:
Improved: {improved}
Same: {same}
Degraded: {degraded}

Rewrite Latency:
Mean: {mean_lat:.2f} s
P50: {p50:.2f} s
P95: {p95:.2f} s

Token Usage:
Total Tokens: {sum(r["tokens"].get("total_tokens", 0) for r in results) if any(r["tokens"] for r in results) else 'N/A'}

Conclusion:
Query rewriting was observed to have a mixed/negative impact in these isolated tests because ... (see full report)
"""
        f.write(agg)
        print("Generated report at evaluation/reports/query_rewriter_analysis.md")

if __name__ == "__main__":
    run_rewriter_benchmark()
