"""Phase 13 Evaluation and Scoring Script.

Compares benchmark results across:
- Phase 12 Baseline
- Phase 13 Goal Guard ON
- Phase 13 Full Reliability (Goal Guard + Argument Repair ON)
"""

import json
import os
import sys
from pathlib import Path
import numpy as np


def normalize_tool(t: str) -> str:
    """Normalize tool names like calendar_list_events -> calendar.list_events."""
    t = t.lower()
    for prefix in ("calendar", "notes", "reminders", "filesystem"):
        if t.startswith(f"{prefix}_"):
            return f"{prefix}.{t[len(prefix)+1:]}"
    return t


def score_result_file(path: str) -> dict:
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}
        
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    
    total = len(cases)
    if total == 0:
        return {"total": 0}
        
    completed_1_srv = 0
    total_1_srv = 0
    
    completed_2_srv = 0
    total_2_srv = 0
    
    completed_3_srv = 0
    total_3_srv = 0
    
    total_completed = 0
    premature_stops = 0
    latencies = []
    llm_calls_list = []
    tool_calls_list = []
    
    for c in cases:
        raw_called = c.get("called_raw", [])
        actual = [normalize_tool(t) for t in raw_called]
        expected = [normalize_tool(t) for t in c.get("expected_tools", [])]
        exp_srv = c.get("expected_servers", [])
        num_srv = len(exp_srv)
        
        # Deduplicate consecutive identical tool calls for sequence checking
        dedup_actual = []
        for t in actual:
            if not dedup_actual or dedup_actual[-1] != t:
                dedup_actual.append(t)
                
        # Check completion
        is_complete = False
        if expected == actual or expected == dedup_actual:
            is_complete = True
        elif set(expected).issubset(set(actual)):
            is_complete = True
            
        # Also check acceptable variants
        for var in c.get("acceptable_variants", []):
            var_norm = [normalize_tool(t) for t in var]
            if var_norm == actual or var_norm == dedup_actual or set(var_norm).issubset(set(actual)):
                is_complete = True
                break
                
        # Category breakdown
        if num_srv <= 1 and c.get("category") == "single_server":
            total_1_srv += 1
            if is_complete:
                completed_1_srv += 1
        elif num_srv == 2 or c.get("category") in ("calendar_notes", "calendar_reminders", "notes_reminders"):
            total_2_srv += 1
            if is_complete:
                completed_2_srv += 1
        elif num_srv >= 3 or c.get("category") == "three_services":
            total_3_srv += 1
            if is_complete:
                completed_3_srv += 1
                
        if is_complete:
            total_completed += 1
        else:
            # Check premature stop
            if len(actual) < len(expected) and len(actual) > 0:
                premature_stops += 1
                
        if "latency_ms" in c:
            latencies.append(c["latency_ms"])
        if "llm_calls" in c:
            llm_calls_list.append(c["llm_calls"])
        tool_calls_list.append(len(actual))
        
    return {
        "total": total,
        "overall_completion": (total_completed / total) * 100 if total else 0,
        "completion_1_service": (completed_1_srv / total_1_srv) * 100 if total_1_srv else 0,
        "n_1_service": f"{completed_1_srv}/{total_1_srv}",
        "completion_2_service": (completed_2_srv / total_2_srv) * 100 if total_2_srv else 0,
        "n_2_service": f"{completed_2_srv}/{total_2_srv}",
        "completion_3_service": (completed_3_srv / total_3_srv) * 100 if total_3_srv else 0,
        "n_3_service": f"{completed_3_srv}/{total_3_srv}",
        "premature_termination_rate": (premature_stops / total) * 100 if total else 0,
        "mean_latency_s": np.mean(latencies) / 1000.0 if latencies else 0,
        "p50_latency_s": np.percentile(latencies, 50) / 1000.0 if latencies else 0,
        "p95_latency_s": np.percentile(latencies, 95) / 1000.0 if latencies else 0,
        "mean_llm_calls": np.mean(llm_calls_list) if llm_calls_list else 0,
        "mean_tool_calls": np.mean(tool_calls_list) if tool_calls_list else 0,
    }


if __name__ == "__main__":
    p12_baseline = "evaluation/results/phase12_context.json"
    p13_guard = "evaluation/results/phase13_goal_guard.json"
    p13_full = "evaluation/results/phase13_full_reliability.json"
    
    print("================ PHASE 13 COMPARATIVE EVALUATION ================")
    if os.path.exists(p12_baseline):
        res12 = score_result_file(p12_baseline)
        print("\n--- PHASE 12 BASELINE ---")
        for k, v in res12.items():
            print(f"  {k}: {v}")
            
    if os.path.exists(p13_guard):
        res13_g = score_result_file(p13_guard)
        print("\n--- PHASE 13 GOAL GUARD ON ---")
        for k, v in res13_g.items():
            print(f"  {k}: {v}")
            
    if os.path.exists(p13_full):
        res13_f = score_result_file(p13_full)
        print("\n--- PHASE 13 FULL RELIABILITY (GUARD + REPAIR) ---")
        for k, v in res13_f.items():
            print(f"  {k}: {v}")
