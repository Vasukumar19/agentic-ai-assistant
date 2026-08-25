#!/usr/bin/env python
"""
Phase 6A MCP benchmark — 20 cases via Qwen3 + test MCP server.
Measures MCP tool selection, argument accuracy, success, etc.
"""

import json
import os
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ["MCP_SERVERS"] = json.dumps([{"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"]}])
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen3:8b")
os.environ.setdefault("OLLAMA_REASONING", "0")

from graph import create_runnable_graph
from mcp_layer.registry import registry

CASES = [
    {"id": "mcp_01_echo", "question": "Use test.echo to echo the message 'hello world'", "category": "single_mcp_read", "expected_tool": "test.echo"},
    {"id": "mcp_02_add", "question": "Use test.add to add 5 and 7", "category": "single_mcp_read", "expected_tool": "test.add"},
    {"id": "mcp_03_lookup", "question": "Use test.lookup to look up query 'foo'", "category": "single_mcp_read", "expected_tool": "test.lookup"},
    {"id": "mcp_04_write", "question": "Use test.write to store key 'mykey' with value 'myvalue'", "category": "single_mcp_write", "expected_tool": "test.write"},
    {"id": "mcp_05_lookup_calc", "question": "Use test.lookup to look up 'foo' and then use calculator to multiply the returned value 42 by 2", "category": "mcp_calc", "expected_tools": ["test.lookup", "calculator"]},
    {"id": "mcp_06_add_calc", "question": "Use test.add to add 10 and 20, then use calculator to multiply the result by 3", "category": "mcp_calc", "expected_tools": ["test.add", "calculator"]},
    {"id": "mcp_07_calc_echo", "question": "Calculate 5 + 7 using calculator, then use test.echo to echo the result", "category": "calc_mcp", "expected_tools": ["calculator", "test.echo"]},
    {"id": "mcp_08_echo_lookup", "question": "Use test.echo to echo 'test' and then use test.lookup to look up 'bar'", "category": "mcp_mcp", "expected_tools": ["test.echo", "test.lookup"]},
    {"id": "mcp_09_add_echo", "question": "Use test.add to add 3 and 4, then use test.echo to echo the result", "category": "mcp_mcp", "expected_tools": ["test.add", "test.echo"]},
    {"id": "mcp_10_web_mcp", "question": "Search the web for population of Japan, then use test.echo to echo the population", "category": "native_mcp", "expected_tools": ["web_search", "test.echo"]},
    {"id": "mcp_11_mcp_web", "question": "Use test.lookup to look up 'test', then search the web for capital of Japan", "category": "mcp_native", "expected_tools": ["test.lookup", "web_search"]},
    {"id": "mcp_12_confirm", "question": "Use test.write to store key 'secret' with value 'data'", "category": "confirmation", "expected_tool": "test.write", "requires_confirmation": True},
    {"id": "mcp_13_fail_invalid", "question": "Use test.add with invalid arguments (missing b)", "category": "failure", "expected_tool": "test.add"},
    {"id": "mcp_14_fail_notfound", "question": "Use test.nonexistent to do something", "category": "failure", "expected_tool": "test.nonexistent"},
    {"id": "mcp_15_fail_timeout", "question": "Use test.fail with mode timeout", "category": "failure", "expected_tool": "test.fail"},
    {"id": "mcp_16_recovery", "question": "Use test.add to add 2 and 3", "category": "recovery", "expected_tool": "test.add"},
    {"id": "mcp_17_mix_calc", "question": "Use test.lookup to get value, then use calculator to add 10 to it", "category": "mcp_calc", "expected_tools": ["test.lookup", "calculator"]},
    {"id": "mcp_18_echo_calc", "question": "Use test.echo to echo 'hello' and then calculate length of hello (5) plus 10 using calculator", "category": "mcp_calc", "expected_tools": ["test.echo", "calculator"]},
    {"id": "mcp_19_lookup_write", "question": "Use test.lookup to look up 'x' and then use test.write to store the value", "category": "mcp_mcp", "expected_tools": ["test.lookup", "test.write"]},
    {"id": "mcp_20_complex", "question": "Use test.add to add 8 and 12, then use calculator to divide the result by 4", "category": "mcp_calc", "expected_tools": ["test.add", "calculator"]},
]

def pct(data, p):
    if not data:
        return None
    s = sorted(data)
    k = (len(s)-1) * p / 100
    f = int(k)
    c = int(k)+1
    if c >= len(s):
        return s[-1]
    d0 = k-f
    return s[f]*(1-d0) + s[c]*d0

def main():
    # ensure MCP discovered
    if not registry._discovered:
        registry.discover()
    print(f"MCP tools: {registry.valid_names()}")
    app = create_runnable_graph()
    results = []
    latencies = []
    mcp_selection_ok = 0
    mcp_arg_ok = 0
    mcp_success = 0
    mcp_total = 0
    traces = []
    print(f"\nRunning {len(CASES)} MCP benchmark cases via Qwen3:8b...\n")
    for i, case in enumerate(CASES, 1):
        q = case["question"]
        cid = case["id"]
        cat = case["category"]
        exp_tool = case.get("expected_tool")
        exp_tools = case.get("expected_tools") or ([exp_tool] if exp_tool else [])
        print(f"[{i}/{len(CASES)}] {cid} ({cat}): {q[:45]!r} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            # handle confirmation case: set policy to require confirmation
            if case.get("requires_confirmation"):
                # temporarily set policy
                norm = registry.get_normalized("test.write")
                if norm:
                    orig = norm.requires_confirmation
                    norm.requires_confirmation = True
                out = app.invoke({"question": q})
                if norm:
                    norm.requires_confirmation = orig
            else:
                out = app.invoke({"question": q})
            dur = int((time.perf_counter() - t0)*1000)
            ans = (out.get("answer") or "")[:150]
            tid = out.get("trace_id")
            evs = out.get("trace_events") or []
            lb = out.get("latency_breakdown") or {}
            status = out.get("execution_status", "completed")
            # check if expected tool was called (via trace)
            called_tools = [e["metadata"]["tool"] for e in evs if e["event_type"] in ("TOOL_CALL","MCP_TOOL_CALL")]
            sel_ok = any(t in called_tools for t in exp_tools) if exp_tools else True
            # arg accuracy: if tool was called, assume args were valid if not error
            arg_ok = True
            for e in evs:
                if e["event_type"] in ("TOOL_CALL","MCP_TOOL_CALL") and e["status"] == "error":
                    # check if error was due to invalid args
                    if "invalid" in str(e.get("error",{}).get("message","")).lower():
                        arg_ok = False
            success = status not in ("error", "timeout") and "error" not in ans.lower()[:20]
            latencies.append(dur)
            traces.append(tid)
            if exp_tools:
                mcp_total += 1
                if sel_ok:
                    mcp_selection_ok += 1
                if arg_ok:
                    mcp_arg_ok += 1
                if success:
                    mcp_success += 1
            results.append({"id": cid, "category": cat, "question": q, "answer_preview": ans, "trace_id": tid, "latency_ms": dur, "events": len(evs), "called_tools": called_tools, "selection_ok": sel_ok, "arg_ok": arg_ok, "success": success, "status": status})
            print(f"-> {dur}ms tools={called_tools} sel={sel_ok} trace={str(tid)[:12]}...")
        except Exception as exc:
            dur = int((time.perf_counter() - t0)*1000)
            print(f"ERROR {exc!r}")
            results.append({"id": cid, "category": cat, "question": q, "error": str(exc)[:300], "latency_ms": dur})
            latencies.append(dur)
    def stats(arr):
        if not arr:
            return {}
        return {"mean": round(statistics.mean(arr),1), "p50": round(pct(arr,50),1), "p95": round(pct(arr,95),1), "max": max(arr), "n": len(arr)}
    summary = {
        "total_latency_ms": stats(latencies),
        "mcp_selection_accuracy": round(mcp_selection_ok/mcp_total*100,1) if mcp_total else None,
        "mcp_arg_accuracy": round(mcp_arg_ok/mcp_total*100,1) if mcp_total else None,
        "mcp_success_rate": round(mcp_success/mcp_total*100,1) if mcp_total else None,
        "mcp_total": mcp_total,
    }
    print("\n" + "="*70)
    print(f"MCP selection: {mcp_selection_ok}/{mcp_total} ({summary['mcp_selection_accuracy']}%)")
    print(f"MCP arg accuracy: {mcp_arg_ok}/{mcp_total} ({summary['mcp_arg_accuracy']}%)")
    print(f"MCP success: {mcp_success}/{mcp_total} ({summary['mcp_success_rate']}%)")
    print(f"Latency: {summary['total_latency_ms']}")
    out_path = Path("evaluation/results/phase6a_mcp_benchmark.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"cases": results, "summary": summary, "traces": traces, "mcp_tools": registry.valid_names()}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")
    if traces:
        print(f"Inspect: python scripts/inspect_trace.py --trace-id {traces[0]}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
