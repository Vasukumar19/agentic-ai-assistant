import json
import time
from nodes.rag_retriever import rag_retriever_node
from evaluation.metrics.retrieval import evaluate_retrieval
from config import RETRIEVAL_MODE

def run_retrieval_benchmark():
    dataset = json.load(open("evaluation/datasets/baseline.json"))
    rag_cases = [c for c in dataset if c["category"] == "rag"]
    
    results = []
    
    print(f"Running Retrieval Benchmark (Mode: {RETRIEVAL_MODE})")
    for case in rag_cases:
        state = {
            "question": case["query"],
            "retrieval_plan": {"rag": True}
        }
        
        try:
            # We add a small sleep to avoid instant rate limit bursts for the rewrite LLM
            time.sleep(1)
            output = rag_retriever_node(state)
            
            retrieved_chunks = output.get("retrieved_chunks", [])
            metrics = evaluate_retrieval(case.get("expected_sources", []), retrieved_chunks)
            
            if metrics:
                results.append({
                    "id": case["id"],
                    "query": case["query"],
                    "expected": case.get("expected_sources", []),
                    "retrieved": retrieved_chunks,
                    "metrics": metrics,
                    "latencies": output.get("retrieval_metrics", {})
                })
                print(f"[{case['id']}] Recall@1: {metrics['recall_at_1']}, MRR: {metrics['mrr']:.3f}")
        except Exception as e:
            print(f"[{case['id']}] Error: {e}")
            
    if not results:
        print("No results!")
        return
        
    rec1 = sum(r["metrics"]["recall_at_1"] for r in results) / len(results)
    rec3 = sum(r["metrics"]["recall_at_3"] for r in results) / len(results)
    rec5 = sum(r["metrics"]["recall_at_5"] for r in results) / len(results)
    rec10 = sum(r["metrics"]["recall_at_10"] for r in results) / len(results)
    mrr = sum(r["metrics"]["mrr"] for r in results) / len(results)
    
    avg_ret_lat = sum(r["latencies"].get("retrieval_latency", 0) for r in results) / len(results)
    avg_rerank_lat = sum(r["latencies"].get("reranker_latency", 0) for r in results) / len(results)
    
    print("\n--- RESULTS ---")
    print(f"Mode: {RETRIEVAL_MODE}")
    print(f"Recall@1: {rec1*100:.1f}%")
    print(f"Recall@3: {rec3*100:.1f}%")
    print(f"Recall@5: {rec5*100:.1f}%")
    print(f"Recall@10: {rec10*100:.1f}%")
    print(f"MRR: {mrr:.3f}")
    print(f"Avg Retrieval Latency: {avg_ret_lat:.3f} s")
    print(f"Avg Rerank Latency: {avg_rerank_lat:.3f} s")

if __name__ == "__main__":
    run_retrieval_benchmark()
