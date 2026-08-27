"""Print detailed 3-service and failure tables for Phase 13.1 report."""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.runners.analyze_phase13_1 import analyze_run

for name, p in [('Phase 13 Original', 'evaluation/results/phase13_goal_guard.json'), ('Repeat A', 'evaluation/results/phase13_repeat_a.json'), ('Repeat B', 'evaluation/results/phase13_repeat_b.json')]:
    res = analyze_run(p)
    print(f"\n=================== {name} (Overall: {res['overall_completion']:.1f}%) ===================")
    print(f"Latency: Mean={res['mean_latency_s']:.2f}s, P50={res['p50_latency_s']:.2f}s, P95={res['p95_latency_s']:.2f}s, P99={res['p99_latency_s']:.2f}s")
    print(f"LLM Calls/query: {res['mean_llm_calls']:.2f}, Tool Calls/query: {res['mean_tool_calls']:.2f}")
    print(f"Budget Exhaustion: {res['budget_exhaustion_rate']:.1f}%, Tool Loops: {res['tool_loop_rate']:.1f}%")
    print(f"\n--- 3-Service Cases ({res['s3_n']}) ---")
    for c in res['s3_cases']:
        print(f"ID: {c['id']} | Complete: {c['is_complete']} | Guard Intervened: {c['guard_intervened']} | Rescued: {c['was_rescued']} | Status: {c['status']}")
        print(f"  Expected: {c['expected']}")
        print(f"  Actual:   {c['actual']}")
