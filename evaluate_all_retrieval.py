import json
from nodes.rag_retriever import rag_retriever_node
from evaluation.metrics.retrieval import evaluate_retrieval
import config

def run_retrieval_benchmark():
    dataset = json.load(open("evaluation/datasets/baseline.json"))
    rag_cases = [c for c in dataset if c["category"] == "rag"]
    
    modes = ["faiss", "hybrid", "rrf", "reranker"]
    
    with open("evaluation/reports/retrieval_phase2_summary.md", "w") as f:
        f.write("# Phase 2 Retrieval Component Benchmarks\n\n")
        f.write("| Mode | Recall@1 | Recall@3 | Recall@5 | MRR | Latency |\n")
        f.write("|---|---|---|---|---|---|\n")
        
        for mode in modes:
            config.RETRIEVAL_MODE = mode
            print(f"Testing {mode}...")
            
            results = []
            for case in rag_cases:
                state = {
                    "question": case["query"],
                    "retrieval_plan": {"rag": True}
                }
                
                output = rag_retriever_node(state)
                retrieved_chunks = output.get("retrieved_chunks", [])
                metrics = evaluate_retrieval(case.get("expected_sources", []), retrieved_chunks)
                
                if metrics:
                    results.append({
                        "metrics": metrics,
                        "latencies": output.get("retrieval_metrics", {})
                    })
                    
            if not results:
                continue
                
            rec1 = sum(r["metrics"]["recall_at_1"] for r in results) / len(results)
            rec3 = sum(r["metrics"]["recall_at_3"] for r in results) / len(results)
            rec5 = sum(r["metrics"]["recall_at_5"] for r in results) / len(results)
            mrr = sum(r["metrics"]["mrr"] for r in results) / len(results)
            
            avg_ret_lat = sum(r["latencies"].get("retrieval_latency", 0) for r in results) / len(results)
            
            f.write(f"| {mode} | {rec1*100:.1f}% | {rec3*100:.1f}% | {rec5*100:.1f}% | {mrr:.3f} | {avg_ret_lat*1000:.1f} ms |\n")
            
if __name__ == "__main__":
    run_retrieval_benchmark()
