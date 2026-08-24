import json
import argparse
import os
import sys
from statistics import mean, median

from evaluation.runners.agent_runner import run_agent
from evaluation.metrics.deterministic import (
    evaluate_routing, evaluate_tool_selection, evaluate_tool_success,
    evaluate_context_coverage, extract_token_usage, calculate_cost
)
from evaluation.metrics.semantic import evaluate_semantic
from config import MODEL_NAME

def run_benchmark(limit=None):
    with open("evaluation/datasets/baseline.json", "r") as f:
        dataset = json.load(f)
        
    if limit:
        dataset = dataset[:limit]
        
    results = []
    
    for case in dataset:
        print(f"Running case: {case['id']}...")
        sys.stdout.flush()
        
        # Execute agent
        final_state, latency, error, failure_category = run_agent(case['query'])
        
        # Determine failure if any (exception)
        passed = True
        details = ""
        
        actual_route = final_state.get("route", "")
        route_correct = evaluate_routing(case.get("expected_route"), actual_route)
        if route_correct is False:
            passed = False
            failure_category = failure_category or "routing_failure"
            details = f"Expected route {case.get('expected_route')} but got {actual_route}"
            
        tool_metrics = evaluate_tool_selection(case.get("expected_tools"), final_state.get("messages", []))
        if tool_metrics and not tool_metrics["exact_match"]:
            passed = False
            failure_category = failure_category or "tool_selection_failure"
            details = f"Tool selection failed. Expected {case.get('expected_tools')} but got {tool_metrics['actual_tools']}"
            
        tool_success = evaluate_tool_success(final_state.get("messages", []))
        if tool_success and tool_success["success_rate"] < 1.0:
            passed = False
            failure_category = failure_category or "tool_execution_failure"
            details = "A tool execution failed."
            
        ctx_coverage = evaluate_context_coverage(case.get("expected_context_keywords"), final_state.get("_combined_context", ""))
        if ctx_coverage is not None and ctx_coverage < 1.0:
            passed = False
            failure_category = failure_category or "retrieval_failure"
            details = f"Context coverage was {ctx_coverage*100}%"
            
        semantic_metrics = evaluate_semantic(
            case["query"], 
            case.get("expected_answer"), 
            final_state.get("answer", ""), 
            final_state.get("_combined_context") if case["category"] == "rag" else None
        )
        
        if "answer_correctness" in semantic_metrics and not semantic_metrics["answer_correctness"].get("correct", True):
            passed = False
            failure_category = failure_category or "answer_generation_failure"
            details = semantic_metrics["answer_correctness"].get("reason", "")
            
        if "faithfulness" in semantic_metrics and semantic_metrics["faithfulness"].get("status") == "unsupported":
            passed = False
            failure_category = failure_category or "hallucination"
            details = semantic_metrics["faithfulness"].get("reason", "")
            
        if error:
            passed = False
            
        tokens = extract_token_usage(final_state.get("messages", []))
        cost = calculate_cost(MODEL_NAME, tokens["input_tokens"], tokens["output_tokens"])
        
        result = {
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "expected_route": case.get("expected_route"),
            "actual_route": actual_route,
            "route_correct": route_correct,
            "expected_tools": case.get("expected_tools"),
            "actual_tools": tool_metrics["actual_tools"] if tool_metrics else [],
            "tool_success": tool_success["success_rate"] == 1.0 if tool_success else None,
            "context_coverage": ctx_coverage,
            "answer": final_state.get("answer", ""),
            "answer_correct": semantic_metrics.get("answer_correctness", {}).get("correct"),
            "faithfulness": semantic_metrics.get("faithfulness", {}).get("status"),
            "latency_ms": int(latency * 1000),
            "llm_calls": tokens["llm_calls"],
            "tokens": tokens,
            "estimated_cost": cost,
            "passed": passed,
            "failure_category": failure_category,
            "details": details
        }
        
        results.append(result)
        
        # Save incrementally
        os.makedirs("evaluation/results", exist_ok=True)
        with open("evaluation/results/baseline_results.json", "w") as f:
            json.dump(results, f, indent=2)
            
    # Generate CSV at the end
    import csv
    with open("evaluation/results/baseline_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        for r in results:
            flat_r = r.copy()
            flat_r["tokens"] = json.dumps(r["tokens"])
            writer.writerow(flat_r)
            
    generate_report(results, len(dataset))

def generate_report(results, total_cases):
    if not results:
        return
        
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
    
    failures = {}
    for r in results:
        if r["failure_category"]:
            failures[r["failure_category"]] = failures.get(r["failure_category"], 0) + 1
            
    report_md = f"""==================================================
AGENT BASELINE EVALUATION
==================================================

Dataset:
  {total_cases} test cases

Routing Accuracy:
  {routing_acc*100:.1f}%

Tool Selection Accuracy:
  {tool_acc*100:.1f}%

Context Keyword Coverage:
  {ctx_cov*100:.1f}%

Answer Accuracy:
  {ans_acc*100:.1f}%

Faithfulness:
  {faith_score*100:.1f}%

Tool Success Rate:
  {tool_succ*100:.1f}%

Average Latency:
  {avg_lat/1000:.2f} s

Median Latency:
  {p50_lat/1000:.2f} s

P95 Latency:
  {p95_lat/1000:.2f} s

Average LLM Calls:
  {llm_calls:.1f}

Average Tokens:
  {tokens_avg:.0f}

Estimated Cost / Query:
  ${avg_cost:.4f}
==================================================

## Failure Analysis
"""
    for f_cat, count in failures.items():
        report_md += f"- {f_cat}: {count} ({count/total_cases*100:.1f}%)\n"

    slowest = sorted(results, key=lambda x: x["latency_ms"], reverse=True)[:5]
    report_md += "\n## Slowest Cases\n"
    for r in slowest:
        report_md += f"- {r['id']}: {r['latency_ms']/1000:.2f}s\n"

    os.makedirs("evaluation/reports", exist_ok=True)
    with open("evaluation/reports/baseline_report.md", "w") as f:
        f.write(report_md)
        
    print("Report generated at evaluation/reports/baseline_report.md")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    
    run_benchmark(args.limit)
