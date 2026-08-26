"""Phase 10 Benchmark Runner — Dynamic Tool Discovery & Namespace Filtering.

Usage:
  python evaluation/runners/phase10_benchmark.py --strategy [none|metadata|llm] --output <filename.json> [--resume]
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
    parser.add_argument("--strategy", type=str, choices=["none", "metadata", "llm"], default="metadata")
    parser.add_argument("--budget", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    budget = args.budget
    disc_strategy = args.strategy
    os.environ["MAX_EXECUTION_STEPS"] = str(budget)
    os.environ["PLANNING_STRATEGY"] = "hybrid"
    os.environ["DISCOVERY_STRATEGY"] = disc_strategy
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["LLM_MODEL"] = "qwen3:8b"
    os.environ["OLLAMA_REASONING"] = "0"
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

    cases = json.loads(Path("evaluation/datasets/phase6c_multiserver.json").read_text(encoding="utf-8"))

    ckpt_dir = Path("evaluation/results")
    ckpt_path = ckpt_dir / f"phase10_{disc_strategy}_checkpoint.json"
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
    print(f"Running cases {start_idx + 1}-{len(cases)} with DISCOVERY_STRATEGY={disc_strategy}\n")

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
            
            # Extract discovery decision metrics
            disc_events = [e for e in evs if e["event_type"] == "DISCOVERY_RESULT"]
            candidate_tools_count = disc_events[0]["metadata"].get("candidate_count") if disc_events else len(registry.valid_names())
            selected_tools_count = disc_events[0]["metadata"].get("selected_count") if disc_events else len(called)
            disc_latency = disc_events[0]["metadata"].get("latency_ms", 0) if disc_events else 0

            llm_n = len(out.get("llm_usage") or [])
            r = {
                "id": cid, "category": case["category"], "question": q,
                "expected_servers": case["expected_servers"],
                "expected_tools": case["expected_tools"],
                "expected_dependencies": case["expected_dependencies"],
                "acceptable_variants": case.get("acceptable_variants", []),
                "called_raw": called,
                "awaiting_confirmation": out.get("execution_status") == "awaiting_confirmation",
                "execution_status": out.get("execution_status"),
                "had_errors": any(e.get("error") for e in evs),
                "answer_preview": (out.get("answer") or "")[:200],
                "trace_id": out.get("trace_id"),
                "latency_ms": dur,
                "discovery_latency_ms": disc_latency,
                "candidate_tools_count": candidate_tools_count,
                "selected_tools_count": selected_tools_count,
                "llm_calls": llm_n,
                "events": len(evs),
            }
            results.append(r)
            completed[cid] = r
            print(f"-> {dur}ms tools={len(called)} candidates={candidate_tools_count}->{selected_tools_count} status={out.get('execution_status')}")
        except Exception as exc:
            dur = int((time.perf_counter() - t0) * 1000)
            print(f"ERROR {exc!r}")
            r = {"id": cid, "category": case["category"], "question": q,
                 "error": str(exc)[:300], "latency_ms": dur}
            results.append(r)
            completed[cid] = r

        ckpt_path.write_text(json.dumps({"strategy": disc_strategy, "cases": list(completed.values())},
                                         indent=2, ensure_ascii=False), encoding="utf-8")

    out_path.write_text(json.dumps({
        "strategy": "hybrid",
        "discovery_strategy": disc_strategy,
        "budget": budget,
        "cases": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved final results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
