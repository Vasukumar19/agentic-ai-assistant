#!/usr/bin/env python
"""
Trace inspection utility — human-readable view of a single trace.
Usage:
  python scripts/inspect_trace.py --trace-id trace_7f91...
  python scripts/inspect_trace.py --last
  python scripts/inspect_trace.py --list
"""

import argparse
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from observability.storage import load_trace, query_traces

def format_ms(ms):
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms/1000:.2f}s"

def inspect(trace_id: str):
    events = load_trace(trace_id)
    if not events:
        print(f"No events found for trace_id={trace_id}")
        return 1
    print(f"\nTrace: {trace_id}")
    # request info from first event
    req = events[0]
    print(f"Request: {req.get('request_id')}  |  {req.get('timestamp')}")
    q = None
    for e in events:
        if e.get("event_type") == "REQUEST":
            q = e.get("metadata", {}).get("question", "")
            break
    if q:
        print(f"Query: {q!r}\n")
    print("="*70)
    for e in events:
        et = e.get("event_type")
        node = e.get("node")
        dur = format_ms(e.get("duration_ms"))
        status = e.get("status")
        meta = e.get("metadata", {})
        err = e.get("error")
        # build summary
        summary = ""
        if et == "REQUEST":
            summary = f'"{meta.get("question","")[:60]}"'
        elif et == "ROUTER":
            summary = f"→ {meta.get('route')} ({meta.get('method')})"
        elif et == "RETRIEVAL":
            if meta.get("skipped"):
                summary = f"skipped ({meta.get('reason')})"
            else:
                mode = meta.get("retrieval_mode", "?")
                chunks = meta.get("retrieved_chunks", meta.get("merged_candidates", "?"))
                summary = f"mode={mode} chunks={chunks}"
        elif et == "CONTEXT_BUILD":
            summary = f"sources={meta.get('sources')} chars={meta.get('combined_chars')}"
        elif et == "PLANNER":
            act = meta.get("action")
            if act == "tool":
                summary = f"→ {meta.get('tool')} {meta.get('arguments')}"
            elif act == "final":
                summary = f"→ final"
            else:
                summary = f"action={act} validation={meta.get('validation_result')}"
        elif et == "TOOL_CALL":
            summary = f"{meta.get('tool')} {meta.get('arguments')}"
        elif et == "TOOL_RESULT":
            summ = meta.get("result_summary", {})
            summary = f"chars={summ.get('result_chars')} preview={summ.get('result_preview','')[:60]!r} error={meta.get('is_error')}"
        elif et == "MEMORY_READ":
            summary = f"profile={meta.get('profile_chars')} semantic={meta.get('semantic_chars')}"
        elif et == "MEMORY_WRITE":
            summary = f"op={meta.get('operation')} fields={meta.get('fields')} sem={meta.get('semantic_count')}"
        elif et == "FINAL_ANSWER":
            preview = meta.get("answer_preview","")[:80]
            summary = f'"{preview}" steps={meta.get("planner_steps")} tools={meta.get("tool_calls")}'
            lb = meta.get("latency_breakdown") or {}
            if lb:
                summary += f"  breakdown={lb}"
        elif et == "TIMEOUT":
            summary = f"timeout {meta.get('timeout_s')}s"
        elif et == "RETRY":
            summary = f"attempt {meta.get('attempt')}/{meta.get('max_retries')} {meta.get('error_type')}"
        elif et == "ERROR":
            summary = f"{err.get('error_type') if err else ''} {meta.get('message','')[:60] if meta else ''}"
        else:
            summary = str(meta)[:80]

        icon = "[OK]" if status == "success" else ("[RETRY]" if status == "retry" else ("[TIMEOUT]" if status == "timeout" else "[ERR]"))
        print(f"{icon} {et:15} {node:18} {dur:>8}  [{status:7}]  {summary}")
        if err and et != "ERROR":
            print(f"   └─ error: {err.get('error_type')}: {err.get('message','')[:100]}")
        if et == "PLANNER" and meta.get("guard_reason"):
            print(f"   └─ guard: {meta.get('guard_reason')}")
    print("="*70)
    # latency summary
    totals = [e for e in events if e.get("event_type") == "FINAL_ANSWER"]
    if totals:
        meta = totals[-1].get("metadata", {})
        print(f"\nTotal latency: {format_ms(meta.get('total_latency_ms'))}")
        lb = meta.get("latency_breakdown", {})
        if lb:
            print("Breakdown:")
            for k, v in lb.items():
                print(f"  {k:20} {format_ms(v)}")
    # llm usage not in events but could be in FINAL_ANSWER?
    return 0

def main():
    ap = argparse.ArgumentParser(description="Inspect a trace")
    ap.add_argument("--trace-id", dest="trace_id", help="trace_id to inspect")
    ap.add_argument("--last", action="store_true", help="inspect last trace")
    ap.add_argument("--list", action="store_true", help="list recent traces")
    ap.add_argument("--json", action="store_true", help="dump raw JSON")
    args = ap.parse_args()
    if args.list:
        recent = query_traces(limit=20)
        print(f"{'trace_id':40} {'request_id':25} {'timestamp':30} {'question'}")
        print("-"*120)
        for r in recent:
            tid = r.get("trace_id","")
            rid = r.get("request_id","")
            ts = r.get("timestamp","")
            q = r.get("metadata",{}).get("question","")[:50]
            print(f"{tid:40} {rid:25} {ts:30} {q!r}")
        return 0
    tid = args.trace_id
    if args.last:
        recent = query_traces(limit=1)
        if not recent:
            print("No traces found")
            return 1
        tid = recent[0].get("trace_id")
    if not tid:
        ap.print_help()
        return 1
    if args.json:
        events = load_trace(tid)
        print(json.dumps(events, indent=2, ensure_ascii=False))
        return 0
    return inspect(tid)

if __name__ == "__main__":
    raise SystemExit(main())
