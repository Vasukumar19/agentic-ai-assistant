"""Phase 13 Benchmark Runner — Goal Fulfillment + MCP Reliability.

Usage:
  python evaluation/runners/phase13_benchmark.py --variant [baseline|guard|full] [--dataset <path>] --output <file.json> [--resume]
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
    parser.add_argument("--variant", type=str, choices=["baseline", "guard", "full"], default="guard")
    parser.add_argument("--dataset", type=str, default="evaluation/datasets/phase6c_multiserver.json")
    parser.add_argument("--budget", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    budget = args.budget
    variant = args.variant
    
    # Configure env vars according to variant
    os.environ["MAX_EXECUTION_STEPS"] = str(budget)
    os.environ["PLANNING_STRATEGY"] = "hybrid"
    os.environ["DISCOVERY_STRATEGY"] = "none"
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["LLM_MODEL"] = "qwen3:8b"
    os.environ["OLLAMA_REASONING"] = "0"
    os.environ["RESULT_AWARE_REPLANNING"] = "on"
    os.environ["PLANNER_COMPLETION_CONTEXT"] = "on"
    
    if variant == "baseline":
        os.environ["GOAL_FULFILLMENT_GUARD"] = "off"
        os.environ["MCP_ARGUMENT_REPAIR"] = "off"
    elif variant == "guard":
        os.environ["GOAL_FULFILLMENT_GUARD"] = "on"
        os.environ["MCP_ARGUMENT_REPAIR"] = "off"
    elif variant == "full":
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

    ckpt_dir = Path("evaluation/results")
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = ckpt_dir / f"phase13_{variant}_checkpoint.json"
    out_path = ckpt_dir / args.output

    completed = {}
    if args.resume and ckpt_path.exists():
        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        for c in ckpt.get("cases", []):
            completed[c["id"]] = c
        print(f"Resumed {len(completed)} completed cases from {ckpt_path}")

    app = create_runnable_graph()
    results = []

    for cid_order, case in enumerate(cases, 1):
        if case["id"] in completed:
            results.append(completed[case["id"]])

    start_idx = len(completed)
    print(f"Running cases {start_idx + 1}-{len(cases)} with VARIANT={variant} (GOAL_GUARD={os.getenv('GOAL_FULFILLMENT_GUARD')}, ARG_REPAIR={os.getenv('MCP_ARGUMENT_REPAIR')})\n")

    for i, case in enumerate(cases[start_idx:], start_idx + 1):
        cid, q = case["id"], case["query"]
        print(f"[{i}/{len(cases)}] {cid}: {q[:42]!r} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            out = app.invoke({"question": q})
            dur = int((time.perf_counter() - t0) * 1000)
            evs = out.get("trace_events") or []
            called = [e["metadata"]["tool"] for e in evs
                      if e["event_type"] in ("TOOL_CALL", "MCP_TOOL_CALL") and "tool" in e["metadata"]]
            
            replan_events = [e for e in evs if e["event_type"] == "REPLAN_START"]
            replan_count = len(replan_events)
            llm_n = len(out.get("llm_usage") or [])

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
                "replan_count": replan_count,
                "llm_calls": llm_n,
                "events": len(evs),
            }
            results.append(r)
            completed[cid] = r
            print(f"-> {dur}ms tools={len(called)} replans={replan_count} status={out.get('execution_status')}")
        except Exception as exc:
            dur = int((time.perf_counter() - t0) * 1000)
            print(f"ERROR {exc!r}")
            r = {"id": cid, "category": case.get("category", "general"), "question": q,
                 "error": str(exc)[:300], "latency_ms": dur}
            results.append(r)
            completed[cid] = r

        ckpt_path.write_text(json.dumps({"variant": variant, "cases": list(completed.values())},
                                         indent=2, ensure_ascii=False), encoding="utf-8")

    out_path.write_text(json.dumps({
        "strategy": "hybrid",
        "variant": variant,
        "goal_fulfillment_guard": os.getenv("GOAL_FULFILLMENT_GUARD"),
        "mcp_argument_repair": os.getenv("MCP_ARGUMENT_REPAIR"),
        "budget": budget,
        "cases": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved final results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
