"""Phase 13.1 Repeatability Benchmark Runner.

Usage:
  python evaluation/runners/phase13_repeatability.py --output evaluation/results/phase13_repeat_a.json [--resume]
  python evaluation/runners/phase13_repeatability.py --output evaluation/results/phase13_repeat_b.json [--resume]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, required=True, help="Path to output results json")
    parser.add_argument("--dataset", type=str, default="evaluation/datasets/phase6c_multiserver.json")
    parser.add_argument("--budget", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    budget = args.budget
    out_file = Path(args.output)
    
    # Configure production environment
    os.environ["MAX_EXECUTION_STEPS"] = str(budget)
    os.environ["PLANNING_STRATEGY"] = "hybrid"
    os.environ["DISCOVERY_STRATEGY"] = "none"
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["LLM_MODEL"] = "qwen3:8b"
    os.environ["OLLAMA_REASONING"] = "0"
    os.environ["RESULT_AWARE_REPLANNING"] = "on"
    os.environ["PLANNER_COMPLETION_CONTEXT"] = "on"
    os.environ["GOAL_FULFILLMENT_GUARD"] = "on"
    os.environ["MCP_ARGUMENT_REPAIR"] = "on"

    os.environ["MCP_SERVERS"] = json.dumps([
        {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
        {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
        {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
    ])

    from graph import create_runnable_graph
    from mcp_layer.registry import registry
    registry._servers = {}
    registry.load_servers_from_config()
    registry.discover(force=True)

    dataset_path = Path(args.dataset)
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))

    ckpt_dir = out_file.parent
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = ckpt_dir / f"{out_file.stem}_checkpoint.json"

    completed = {}
    if args.resume and ckpt_path.exists():
        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        for c in ckpt.get("cases", []):
            completed[c["id"]] = c
        print(f"Resumed {len(completed)} completed cases from {ckpt_path}")

    app = create_runnable_graph()
    results = []

    for case in cases:
        if case["id"] in completed:
            results.append(completed[case["id"]])

    start_idx = len(completed)
    print(f"Running cases {start_idx + 1}-{len(cases)} -> {out_file}\n")

    t_start_all = time.time()

    for i, case in enumerate(cases[start_idx:], start_idx + 1):
        cid, q = case["id"], case["query"]
        print(f"[{i:02d}/{len(cases)}] {cid}: {q[:38]!r} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            out = app.invoke({"question": q})
            dur = int((time.perf_counter() - t0) * 1000)
            evs = out.get("trace_events") or []
            called = [e["metadata"]["tool"] for e in evs
                      if e["event_type"] in ("TOOL_CALL", "MCP_TOOL_CALL") and "tool" in e["metadata"]]
            
            goal_checks = [e for e in evs if e["event_type"] == "GOAL_CHECK"]
            goal_incompletes = [e for e in evs if e["event_type"] == "GOAL_INCOMPLETE"]
            arg_repairs = [e for e in evs if e["event_type"] == "ARGUMENT_REPAIR"]
            replan_events = [e for e in evs if e["event_type"] == "REPLAN_START"]
            
            # Did the model try to finalize early?
            guard_intervened = len(goal_incompletes) > 0
            is_completed = out.get("execution_status") == "completed"
            was_rescued = guard_intervened and is_completed

            r = {
                "id": cid, "category": case.get("category", "general"), "question": q,
                "expected_servers": case.get("expected_servers", []),
                "expected_tools": case.get("expected_tools", []),
                "expected_dependencies": case.get("expected_dependencies", []),
                "acceptable_variants": case.get("acceptable_variants", []),
                "called_raw": called,
                "awaiting_confirmation": out.get("execution_status") == "awaiting_confirmation",
                "execution_status": out.get("execution_status"),
                "had_errors": any(e.get("error") for e in evs),
                "answer_preview": (out.get("answer") or "")[:200],
                "trace_id": out.get("trace_id"),
                "latency_ms": dur,
                "replan_count": len(replan_events),
                "goal_check_count": len(goal_checks),
                "goal_incomplete_count": len(goal_incompletes),
                "guard_intervened": guard_intervened,
                "was_rescued": was_rescued,
                "argument_repair_count": len(arg_repairs),
                "llm_calls": len(out.get("llm_usage") or []),
                "events": len(evs),
            }
            results.append(r)
            completed[cid] = r
            print(f"-> {dur}ms tools={len(called)} guard_rejects={len(goal_incompletes)} status={out.get('execution_status')}")
        except Exception as exc:
            dur = int((time.perf_counter() - t0) * 1000)
            print(f"ERROR {exc!r}")
            r = {"id": cid, "category": case.get("category", "general"), "question": q,
                 "error": str(exc)[:300], "latency_ms": dur, "guard_intervened": False, "was_rescued": False}
            results.append(r)
            completed[cid] = r

        ckpt_path.write_text(json.dumps({"cases": list(completed.values())}, indent=2, ensure_ascii=False), encoding="utf-8")

    total_time_s = time.time() - t_start_all
    out_file.write_text(json.dumps({
        "environment": {
            "model": "qwen3:8b",
            "ollama_reasoning": 0,
            "planning_strategy": "hybrid",
            "execution_budget": budget,
            "result_aware_replanning": "on",
            "planner_completion_context": "on",
            "goal_fulfillment_guard": "on",
            "mcp_argument_repair": "on",
            "dataset": args.dataset,
            "total_cases": len(results),
            "total_time_s": total_time_s,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "cases": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved final results to {out_file} (Total time: {total_time_s:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
