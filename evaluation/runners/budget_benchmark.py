#!/usr/bin/env python
"""Resumable budget benchmark — saves checkpoint after each case.

Usage:
  python evaluation/runners/budget_benchmark.py --budget 10 [--resume]

Env vars (auto-set from --budget):
  MAX_EXECUTION_STEPS, PLANNING_STRATEGY=hybrid
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
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    budget = args.budget
    os.environ["MAX_EXECUTION_STEPS"] = str(budget)
    os.environ["PLANNING_STRATEGY"] = "hybrid"
    os.environ["MCP_SERVERS"] = json.dumps([
        {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
        {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
        {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
    ])
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["LLM_MODEL"] = "qwen3:8b"
    os.environ["OLLAMA_REASONING"] = "0"

    from graph import create_runnable_graph
    from mcp_layer.registry import registry
    registry._servers = {}
    registry.load_servers_from_config()
    registry.discover(force=True)

    cases = json.loads(Path("evaluation/datasets/phase6c_multiserver.json").read_text(encoding="utf-8"))

    ckpt_dir = Path("evaluation/results")
    ckpt_path = ckpt_dir / f"phase8_budget{budget}_checkpoint.json"
    out_name = args.output or f"phase8_hybrid_budget{budget}_results.json"
    out_path = ckpt_dir / out_name

    # Load checkpoint
    completed = {}
    if args.resume and ckpt_path.exists():
        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        for c in ckpt.get("cases", []):
            completed[c["id"]] = c
        print(f"Resumed {len(completed)} completed cases from {ckpt_path}")

    app = create_runnable_graph()
    results, traces, latencies, llm_calls = [], [], [], []

    # Restore completed results
    for cid_order, case in enumerate(cases, 1):
        if case["id"] in completed:
            r = completed[case["id"]]
            results.append(r)
            traces.append(r.get("trace_id"))
            latencies.append(r.get("latency_ms", 0))
            llm_calls.append(r.get("llm_calls", 0))

    start_idx = len(completed)
    print(f"Running cases {start_idx + 1}-{len(cases)} with MAX_EXECUTION_STEPS={budget}, PLANNING_STRATEGY=hybrid\n")

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
            llm_n = len(out.get("llm_usage") or [])
            llm_calls.append(llm_n)
            latencies.append(dur)
            traces.append(out.get("trace_id"))
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
                "llm_calls": llm_n,
                "events": len(evs),
            }
            results.append(r)
            completed[cid] = r
            print(f"-> {dur}ms tools={len(called)} status={out.get('execution_status')}")
        except Exception as exc:
            dur = int((time.perf_counter() - t0) * 1000)
            print(f"ERROR {exc!r}")
            r = {"id": cid, "category": case["category"], "question": q,
                 "error": str(exc)[:300], "latency_ms": dur}
            results.append(r)
            completed[cid] = r

        # Persist checkpoint after every case
        ckpt_path.write_text(json.dumps({"budget": budget, "cases": list(completed.values())},
                                         indent=2, ensure_ascii=False), encoding="utf-8")

    # Persist final results
    out_path.write_text(json.dumps({
        "strategy": "hybrid",
        "budget": budget,
        "cases": results,
        "traces": traces,
        "raw_summary": {
            "mean_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1),
            "avg_llm_calls": round(sum(llm_calls) / max(len(llm_calls), 1), 2),
            "n": len(latencies),
        }
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
