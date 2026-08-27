"""Phase 13.1 Repeatability and Statistical Analysis Script.

Computes:
1. Overall metrics across Phase 12, Phase 13 Original, Repeat A, Repeat B
2. 1-service, 2-service, 3-service scaling
3. Goal Guard Intervention & Rescue Rates
4. 3-Service Case-by-Case Deep Dive Table
5. Failure Taxonomy & Classification
6. Latency distributions (P50, P95, P99)
"""

import json
import os
import sys
from pathlib import Path
import numpy as np


def normalize_tool(t: str) -> str:
    if not t:
        return ""
    t = t.lower()
    for prefix in ("calendar", "notes", "reminders", "filesystem"):
        if t.startswith(f"{prefix}_"):
            return f"{prefix}.{t[len(prefix)+1:]}"
    return t


def analyze_run(path: str) -> dict:
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}
        
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    total = len(cases)
    if total == 0:
        return {"total": 0}
        
    # Service buckets
    s1_cases, s2_cases, s3_cases = [], [], []
    
    # Counts
    completed_total = 0
    premature_stops = 0
    budget_exhausted = 0
    tool_loops = 0
    unnecessary_tools = 0
    
    # Guard analytics
    guard_interventions = 0
    guard_rescues = 0
    guard_failures_after_int = 0
    guard_not_needed = 0
    planner_only_successes = 0
    
    latencies = []
    llm_calls = []
    tool_calls = []
    
    for c in cases:
        raw_called = c.get("called_raw", [])
        actual = [normalize_tool(t) for t in raw_called]
        expected = [normalize_tool(t) for t in c.get("expected_tools", [])]
        exp_srv = c.get("expected_servers", [])
        num_srv = len(exp_srv)
        cat = c.get("category", "")
        
        # Deduplicated actual
        dedup_actual = []
        for t in actual:
            if not dedup_actual or dedup_actual[-1] != t:
                dedup_actual.append(t)
                
        is_complete = False
        if expected == actual or expected == dedup_actual:
            is_complete = True
        elif set(expected).issubset(set(actual)):
            is_complete = True
            
        for var in c.get("acceptable_variants", []):
            var_norm = [normalize_tool(t) for t in var]
            if var_norm == actual or var_norm == dedup_actual or set(var_norm).issubset(set(actual)):
                is_complete = True
                break
                
        # Status checks
        status = c.get("execution_status", "")
        if status == "budget_exhausted":
            budget_exhausted += 1
        elif status == "repeated_tool_call":
            tool_loops += 1
            
        if any(t not in expected for t in actual):
            unnecessary_tools += 1
            
        # Bucketing
        case_info = {
            "id": c.get("id"),
            "query": c.get("question"),
            "expected": expected,
            "actual": actual,
            "is_complete": is_complete,
            "status": status,
            "latency_ms": c.get("latency_ms", 0),
            "guard_intervened": c.get("guard_intervened", False) or c.get("goal_incomplete_count", 0) > 0,
            "was_rescued": c.get("was_rescued", False) or (c.get("goal_incomplete_count", 0) > 0 and is_complete),
        }
        
        if num_srv <= 1 and cat == "single_server":
            s1_cases.append(case_info)
        elif num_srv == 2 or cat in ("calendar_notes", "calendar_reminders", "notes_reminders"):
            s2_cases.append(case_info)
        elif num_srv >= 3 or cat == "three_services":
            s3_cases.append(case_info)
            
        if is_complete:
            completed_total += 1
            if case_info["guard_intervened"]:
                guard_rescues += 1
            else:
                planner_only_successes += 1
        else:
            if len(actual) < len(expected) and len(actual) > 0:
                premature_stops += 1
            if case_info["guard_intervened"]:
                guard_failures_after_int += 1
                
        if case_info["guard_intervened"]:
            guard_interventions += 1
        else:
            guard_not_needed += 1
            
        if "latency_ms" in c:
            latencies.append(c["latency_ms"])
        if "llm_calls" in c:
            llm_calls.append(c["llm_calls"])
        tool_calls.append(len(actual))
        
    s1_comp = sum(1 for x in s1_cases if x["is_complete"])
    s2_comp = sum(1 for x in s2_cases if x["is_complete"])
    s3_comp = sum(1 for x in s3_cases if x["is_complete"])
    
    return {
        "total": total,
        "overall_completion": (completed_total / total) * 100,
        "s1_completion": (s1_comp / len(s1_cases) * 100) if s1_cases else 0,
        "s1_n": f"{s1_comp}/{len(s1_cases)}",
        "s2_completion": (s2_comp / len(s2_cases) * 100) if s2_cases else 0,
        "s2_n": f"{s2_comp}/{len(s2_cases)}",
        "s3_completion": (s3_comp / len(s3_cases) * 100) if s3_cases else 0,
        "s3_n": f"{s3_comp}/{len(s3_cases)}",
        "premature_termination_rate": (premature_stops / total) * 100,
        "budget_exhaustion_rate": (budget_exhausted / total) * 100,
        "tool_loop_rate": (tool_loops / total) * 100,
        "unnecessary_tool_rate": (unnecessary_tools / total) * 100,
        "mean_latency_s": np.mean(latencies) / 1000.0 if latencies else 0,
        "p50_latency_s": np.percentile(latencies, 50) / 1000.0 if latencies else 0,
        "p95_latency_s": np.percentile(latencies, 95) / 1000.0 if latencies else 0,
        "p99_latency_s": np.percentile(latencies, 99) / 1000.0 if latencies else 0,
        "mean_llm_calls": np.mean(llm_calls) if llm_calls else 0,
        "mean_tool_calls": np.mean(tool_calls) if tool_calls else 0,
        "guard_analytics": {
            "guard_interventions": guard_interventions,
            "guard_intervention_rate": (guard_interventions / total) * 100,
            "guard_rescues": guard_rescues,
            "guard_rescue_rate": (guard_rescues / guard_interventions * 100) if guard_interventions else 0,
            "guard_failures_after_intervention": guard_failures_after_int,
            "guard_not_needed": guard_not_needed,
            "planner_only_successes": planner_only_successes,
        },
        "s3_cases": s3_cases,
    }


def print_comparison():
    p12 = "evaluation/results/phase12_context.json"
    p13 = "evaluation/results/phase13_goal_guard.json"
    rep_a = "evaluation/results/phase13_repeat_a.json"
    rep_b = "evaluation/results/phase13_repeat_b.json"
    
    print("=================== PHASE 13.1 REPEATABILITY EVALUATION ===================")
    for name, p in [("Phase 12 Baseline", p12), ("Phase 13 Original", p13), ("Repeat A", rep_a), ("Repeat B", rep_b)]:
        if os.path.exists(p):
            res = analyze_run(p)
            print(f"\n--- {name} ---")
            print(f"  Overall Completion: {res.get('overall_completion'):.1f}%")
            print(f"  1-Service: {res.get('s1_completion'):.1f}% ({res.get('s1_n')})")
            print(f"  2-Service: {res.get('s2_completion'):.1f}% ({res.get('s2_n')})")
            print(f"  3-Service: {res.get('s3_completion'):.1f}% ({res.get('s3_n')})")
            print(f"  Premature Stops: {res.get('premature_termination_rate'):.1f}%")
            print(f"  Mean Latency: {res.get('mean_latency_s'):.2f}s (P95: {res.get('p95_latency_s'):.2f}s)")
            ga = res.get("guard_analytics", {})
            print(f"  Guard Interventions: {ga.get('guard_interventions')} ({ga.get('guard_intervention_rate', 0):.1f}%)")
            print(f"  Guard Rescues: {ga.get('guard_rescues')} (Rescue Rate: {ga.get('guard_rescue_rate', 0):.1f}%)")


if __name__ == "__main__":
    print_comparison()
