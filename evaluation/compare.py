import json
import sys
import argparse
from statistics import mean, median

def load_metrics(filepath):
    with open(filepath, "r") as f:
        results = json.load(f)
    
    total = len(results)
    if total == 0:
        return {}
        
    valid_routes = [r for r in results if r["route_correct"] is not None]
    routing_acc = sum(1 for r in valid_routes if r["route_correct"]) / len(valid_routes) if valid_routes else 0
    
    valid_tools = [r for r in results if r["expected_tools"] is not None]
    tool_acc = sum(1 for r in valid_tools if set(r["expected_tools"]) == set(r["actual_tools"])) / len(valid_tools) if valid_tools else 0
    
    valid_tool_succ = [r for r in results if r["tool_success"] is not None]
    tool_succ = sum(1 for r in valid_tool_succ if r["tool_success"]) / len(valid_tool_succ) if valid_tool_succ else 0
    
    valid_ans = [r for r in results if r["answer_correct"] is not None]
    ans_acc = sum(1 for r in valid_ans if r["answer_correct"]) / len(valid_ans) if valid_ans else 0
    
    valid_faith = [r for r in results if r["faithfulness"] is not None]
    faith_score = sum(1 for r in valid_faith if r["faithfulness"] == "supported") / len(valid_faith) if valid_faith else 0
    
    valid_ctx = [r for r in results if r["context_coverage"] is not None]
    ctx_cov = mean(r["context_coverage"] for r in valid_ctx) if valid_ctx else 0
    
    latencies = [r["latency_ms"] for r in results]
    latencies.sort()
    avg_lat = mean(latencies)
    p50_lat = median(latencies)
    p95_lat = latencies[int(len(latencies) * 0.95)] if latencies else 0
    
    llm_calls = mean(r["llm_calls"] for r in results)
    tokens_avg = mean(r["tokens"]["total_tokens"] for r in results)
    
    valid_costs = [r["estimated_cost"] for r in results if r["estimated_cost"] is not None]
    avg_cost = mean(valid_costs) if valid_costs else 0
    
    return {
        "Routing Accuracy": routing_acc * 100,
        "Tool Selection Accuracy": tool_acc * 100,
        "Tool Success Rate": tool_succ * 100,
        "Context Coverage": ctx_cov * 100,
        "Answer Accuracy": ans_acc * 100,
        "Faithfulness": faith_score * 100,
        "Average Latency (s)": avg_lat / 1000,
        "P95 Latency (s)": p95_lat / 1000,
        "LLM Calls": llm_calls,
        "Tokens": tokens_avg,
        "Estimated Cost": avg_cost
    }

def compare(baseline_path, new_path):
    base_metrics = load_metrics(baseline_path)
    new_metrics = load_metrics(new_path)
    
    print(f"{'Metric':<30} {'Baseline':<10} {'New':<10} {'Delta':<10}")
    print("-" * 62)
    
    for key in base_metrics:
        b = base_metrics[key]
        n = new_metrics[key]
        delta = n - b
        
        if key in ["Average Latency (s)", "P95 Latency (s)", "LLM Calls", "Tokens", "Estimated Cost"]:
            delta_pct = (delta / b * 100) if b > 0 else 0
            print(f"{key:<30} {b:<10.2f} {n:<10.2f} {delta_pct:+.1f}%")
        else:
            print(f"{key:<30} {b:<9.1f}% {n:<9.1f}% {delta:+.1f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", help="Path to baseline results JSON")
    parser.add_argument("new", help="Path to new results JSON")
    args = parser.parse_args()
    
    compare(args.baseline, args.new)
