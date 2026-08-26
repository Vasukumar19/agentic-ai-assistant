#!/usr/bin/env python
"""Phase 7 strategy benchmark - runs the 60-case dataset under a given PLANNING_STRATEGY."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

STRATEGY = os.environ.get("PLANNING_STRATEGY", "dependency")
os.environ["MCP_SERVERS"] = json.dumps([
    {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
    {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
    {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
])
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["LLM_MODEL"] = "qwen3:8b"
os.environ["OLLAMA_REASONING"] = "0"
os.environ["PLANNING_STRATEGY"] = STRATEGY

from graph import create_runnable_graph  # noqa: E402


def main():
    from mcp_layer.registry import registry
    registry._servers = {}
    registry.load_servers_from_config()
    registry.discover(force=True)
    cases = json.loads(Path("evaluation/datasets/phase6c_multiserver.json").read_text(encoding="utf-8"))
    app = create_runnable_graph()
    results, traces, latencies, planner_lats, llm_calls = [], [], [], [], []
    print(f"Running {len(cases)} cases with PLANNING_STRATEGY={os.environ['PLANNING_STRATEGY']}\n")
    for i, case in enumerate(cases, 1):
        cid, q = case["id"], case["query"]
        print(f"[{i}/{len(cases)}] {cid}: {q[:42]!r} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            out = app.invoke({"question": q})
            dur = int((time.perf_counter() - t0) * 1000)
            evs = out.get("trace_events") or []
            lb = out.get("latency_breakdown") or {}
            called = [e["metadata"]["tool"] for e in evs
                      if e["event_type"] in ("TOOL_CALL", "MCP_TOOL_CALL") and "tool" in e["metadata"]]
            llm_calls.append(len(out.get("llm_usage") or []))
            if lb.get("planner"):
                planner_lats.append(lb["planner"])
            latencies.append(dur)
            traces.append(out.get("trace_id"))
            results.append({
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
                "llm_calls": len(out.get("llm_usage") or []),
                "events": len(evs),
            })
            print(f"-> {dur}ms tools={len(called)} status={out.get('execution_status')}")
        except Exception as exc:
            print(f"ERROR {exc!r}")
            results.append({"id": cid, "category": case["category"], "question": q,
                            "error": str(exc)[:300], "latency_ms": int((time.perf_counter() - t0) * 1000)})
    out_name = f"phase7_{os.environ['PLANNING_STRATEGY']}_results.json"
    out_path = Path("evaluation/results") / out_name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"strategy": os.environ["PLANNING_STRATEGY"], "cases": results,
                   "traces": traces,
                   "raw_summary": {"mean_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1),
                                    "avg_llm_calls": round(sum(llm_calls) / max(len(llm_calls), 1), 2),
                                    "n": len(latencies)}},
                  f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
