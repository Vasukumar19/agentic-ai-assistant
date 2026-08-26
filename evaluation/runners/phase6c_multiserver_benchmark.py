#!/usr/bin/env python
"""
Phase 6C multi-server MCP benchmark — 60 Qwen3 cases across calendar/notes/reminders.
Capability + efficiency metrics. Dataset is frozen; evaluator derives results post-hoc.
"""

import json
import os
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ["MCP_SERVERS"] = json.dumps([
    {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
    {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
    {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
])
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen3:8b")
os.environ.setdefault("OLLAMA_REASONING", "0")

from graph import create_runnable_graph


def pct(data, p):
    if not data:
        return None
    s = sorted(data)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = int(k) + 1
    if c >= len(s):
        return s[-1]
    return s[f] * (1 - (k - f)) + s[c] * (k - f)


def main():
    from mcp_layer.registry import registry
    t_disc = time.perf_counter()
    registry._servers = {}
    registry.load_servers_from_config()
    n_tools = registry.discover(force=True)
    disc_ms = int((time.perf_counter() - t_disc) * 1000)
    print(f"Discovery: {n_tools} tools in {disc_ms}ms")

    cases = json.loads(Path("evaluation/datasets/phase6c_multiserver.json").read_text(encoding="utf-8"))
    app = create_runnable_graph()

    results = []
    latencies = []
    planner_lats = []
    traces = []

    print(f"\nRunning {len(cases)} Phase 6C cases via Qwen3:8b...\n")
    for i, case in enumerate(cases, 1):
        cid = case["id"]
        q = case["query"]
        print(f"[{i}/{len(cases)}] {cid} ({case['category']}): {q[:45]!r} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            out = app.invoke({"question": q})
            dur = int((time.perf_counter() - t0) * 1000)
            evs = out.get("trace_events") or []
            lb = out.get("latency_breakdown") or {}
            called = [e["metadata"]["tool"] for e in evs
                      if e["event_type"] in ("TOOL_CALL", "MCP_TOOL_CALL") and "tool" in e["metadata"]]
            errors = [e for e in evs if e.get("error")]
            awaiting = out.get("execution_status") == "awaiting_confirmation"
            ans = (out.get("answer") or "")[:200]
            tid = out.get("trace_id")
            if lb.get("planner"):
                planner_lats.append(lb["planner"])
            latencies.append(dur)
            traces.append(tid)
            results.append({
                "id": cid, "category": case["category"], "question": q,
                "expected_servers": case["expected_servers"],
                "expected_tools": case["expected_tools"],
                "expected_dependencies": case["expected_dependencies"],
                "acceptable_variants": case["acceptable_variants"],
                "requires_confirmation_case": case["requires_confirmation"],
                "called_raw": called,
                "awaiting_confirmation": awaiting,
                "had_errors": bool(errors),
                "execution_status": out.get("execution_status"),
                "answer_preview": ans,
                "trace_id": tid,
                "latency_ms": dur,
                "events": len(evs),
                "latency_breakdown": lb,
            })
            print(f"-> {dur}ms tools={len(called)} await={awaiting} trace={str(tid)[:12]}...")
        except Exception as exc:
            dur = int((time.perf_counter() - t0) * 1000)
            print(f"ERROR {exc!r}")
            results.append({"id": cid, "category": case["category"], "question": q,
                            "error": str(exc)[:300], "latency_ms": dur})
            latencies.append(dur)

    out_path = Path("evaluation/results/phase6c_multiserver_benchmark.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def stats(arr):
        if not arr:
            return {}
        return {"mean": round(statistics.mean(arr), 1),
                "p50": round(pct(arr, 50), 1), "p95": round(pct(arr, 95), 1),
                "max": max(arr), "min": min(arr), "n": len(arr)}

    raw_summary = {
        "discovery_ms": disc_ms,
        "discovered_tools": n_tools,
        "total_latency_ms": stats(latencies),
        "planner_latency_ms": stats(planner_lats),
        "executed_cases": sum(1 for r in results if "error" not in r),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"cases": results, "raw_summary": raw_summary, "traces": traces}, f, indent=2, ensure_ascii=False)
    print("\n" + "=" * 70)
    print(f"Executed: {raw_summary['executed_cases']}/{len(cases)}")
    print(f"Latency: {raw_summary['total_latency_ms']}")
    print(f"Saved: {out_path}")
    print("(Derived capability/efficiency evaluation runs separately — dataset expectations untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
