import json
import os
import argparse
import time

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if not args.live:
        os.environ["MOCK_LLM"] = "1"
        print("Running with Mock LLM for deterministic failure analysis.")

    # NOW we import the graph
    from graph import create_runnable_graph

    def extract_actual_sequence(state):
        seq = []
        plan = state.get("retrieval_plan", {})
        if plan.get("rag"):
            seq.append("rag")
        if plan.get("profile") or plan.get("semantic"):
            seq.append("memory_search")
            
        messages = state.get("messages", [])
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for call in msg.tool_calls:
                    seq.append(call["name"])
        return seq

    dataset = json.load(open("evaluation/datasets/phase3_multistep.json"))[:args.limit]
    
    app = create_runnable_graph()
    
    results = []
    
    for case in dataset:
        print(f"Testing: {case['query']}")
        state = {"question": case["query"]}
        
        start_time = time.time()
        try:
            final_state = app.invoke(state)
            actual_seq = extract_actual_sequence(final_state)
            error = None
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                print("Hit rate limit. Stopping.")
                break
            final_state = state
            actual_seq = extract_actual_sequence(final_state)
            error = str(e)
            
        latency = time.time() - start_time
        
        expected_seq = case.get("expected_sequence", [])
        
        failure_mode = None
        if actual_seq != expected_seq:
            if not actual_seq:
                failure_mode = "missing_tool"
            elif len(actual_seq) < len(expected_seq):
                if actual_seq == expected_seq[:len(actual_seq)]:
                    failure_mode = "premature_stop"
                else:
                    failure_mode = "missing_tool"
            elif set(actual_seq) - set(expected_seq):
                failure_mode = "unnecessary_tool"
            elif set(expected_seq) - set(actual_seq):
                failure_mode = "missing_tool"
            elif sorted(actual_seq) == sorted(expected_seq) and actual_seq != expected_seq:
                failure_mode = "wrong_order"
            else:
                failure_mode = "wrong_tool"
                
        results.append({
            "id": case["id"],
            "query": case["query"],
            "expected": expected_seq,
            "actual": actual_seq,
            "failure_mode": failure_mode,
            "latency": latency,
            "error": error
        })
        time.sleep(0.1)
        
    total = len(results)
    if total == 0:
        exit(0)
        
    correct_selection = sum(1 for r in results if set(r["actual"]) == set(r["expected"]))
    correct_sequence = sum(1 for r in results if r["actual"] == r["expected"])
    
    failures = [r for r in results if r["failure_mode"]]
    failure_counts = {}
    for f in failures:
        failure_counts[f["failure_mode"]] = failure_counts.get(f["failure_mode"], 0) + 1
        
    avg_latency = sum(r["latency"] for r in results) / total
    
    report = f"""# Phase 3 Baseline (Current ReAct Agent)

Total cases run: {total}

## Metrics
- Tool Selection Accuracy: {correct_selection / total * 100:.1f}%
- Tool Sequence Accuracy: {correct_sequence / total * 100:.1f}%
- Multi-Step Completion Rate: {correct_sequence / total * 100:.1f}%
- Average Latency: {avg_latency:.2f}s

## Failure Analysis
| Failure Mode | Count |
|---|---|
"""
    for k, v in failure_counts.items():
        report += f"| {k} | {v} |\n"
        
    report += "\n## Failed Cases\n"
    for f in failures:
        report += f"- Query: {f['query']}\n  Expected: {f['expected']}\n  Actual: {f['actual']}\n  Failure: {f['failure_mode']}\n\n"
        
    with open("evaluation/reports/phase3_baseline.md", "w") as f:
        f.write(report)
        
    print("Baseline report saved.")
