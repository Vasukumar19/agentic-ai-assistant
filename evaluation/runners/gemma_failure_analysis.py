"""
Failure classification script for Gemma 3 12B vs Qwen3:8b (Phase 9 vs Phase 8).

Classifies each failed case into one of 16 canonical failure categories:
MODEL_FAILURE, PLANNING_FAILURE, DEPENDENCY_FAILURE, TOOL_SELECTION_FAILURE,
ARGUMENT_FAILURE, PREMATURE_TERMINATION, NON_CONVERGENCE, REPEATED_TOOL,
UNNECESSARY_TOOL, BUDGET_TOO_LOW, VERIFIER_FAILURE, MCP_FAILURE, TIMEOUT,
NETWORK, INFRASTRUCTURE, EVALUATOR_FAILURE.
"""

import json
from pathlib import Path


def classify_case(r: dict) -> str:
    if "error" in r:
        err = str(r["error"]).lower()
        if "timeout" in err:
            return "TIMEOUT"
        if "taskgroup" in err or "unhandled errors" in err:
            return "INFRASTRUCTURE"
        if "dict" in err or "attribute" in err or "lower" in err:
            return "MODEL_FAILURE"
        return "MCP_FAILURE"

    status = r.get("execution_status")
    if status == "timeout":
        return "TIMEOUT"
    if status == "budget_exhausted":
        return "BUDGET_TOO_LOW"
    if status == "repeated_tool_call":
        return "REPEATED_TOOL"
    if status == "running":
        return "PREMATURE_TERMINATION"
    if status == "error":
        return "PLANNING_FAILURE"

    # Check tool and dependency correctness
    expected_tools = r.get("expected_tools") or []
    called_raw = r.get("called_raw") or []
    expected_deps = r.get("expected_dependencies") or []

    called_set = set(called_raw)
    exp_set = set(expected_tools)

    if expected_tools and not exp_set.issubset(called_set):
        return "TOOL_SELECTION_FAILURE"

    # Check dependencies
    for a, b in expected_deps:
        if a in called_raw and b in called_raw:
            if called_raw.index(a) > called_raw.index(b):
                return "DEPENDENCY_FAILURE"

    if len(called_raw) > len(expected_tools):
        return "UNNECESSARY_TOOL"

    if status != "completed":
        return "NON_CONVERGENCE"

    return "SUCCESS"


def analyze():
    gemma_path = Path("evaluation/results/phase9_gemma_budget10_results.json")
    qwen_path = Path("evaluation/results/phase8_hybrid_budget10_results.json")

    gemma_data = json.loads(gemma_path.read_text(encoding="utf-8"))["cases"]
    qwen_data = json.loads(qwen_path.read_text(encoding="utf-8"))["cases"]

    gemma_counts = {}
    qwen_counts = {}

    for c in gemma_data:
        cat = classify_case(c)
        gemma_counts[cat] = gemma_counts.get(cat, 0) + 1

    for c in qwen_data:
        cat = classify_case(c)
        qwen_counts[cat] = qwen_counts.get(cat, 0) + 1

    print("=== FAILURE CLASSIFICATION COMPARISON (n=60) ===")
    all_cats = sorted(set(list(gemma_counts.keys()) + list(qwen_counts.keys())))
    print(f"{'Category':<25} | {'Qwen3:8b':<10} | {'Gemma3:12b':<10} | {'Delta':<8}")
    print("-" * 60)
    for cat in all_cats:
        q = qwen_counts.get(cat, 0)
        g = gemma_counts.get(cat, 0)
        d = g - q
        sign = "+" if d > 0 else ""
        print(f"{cat:<25} | {q:<10} | {g:<10} | {sign}{d:<8}")


if __name__ == "__main__":
    analyze()
