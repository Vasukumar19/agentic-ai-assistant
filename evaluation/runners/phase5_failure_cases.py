#!/usr/bin/env python
"""
Phase 5 failure debugging — 5 intentional failures, verify trace makes root cause obvious.
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen3:8b")
os.environ.setdefault("OLLAMA_REASONING", "0")

from graph import create_runnable_graph
from observability.storage import load_trace

CASES = [
    {"id": "fail_01_tool_arg", "question": "calculate 5% of 100000000", "expect": "TOOL_ARGUMENT_ERROR or validation", "why": "5% of ... is not valid python expression for calculator (needs 5/100*... )"},
    {"id": "fail_02_network", "question": "What is the population of Atlantis?", "expect": "NETWORK_ERROR or RETRIEVAL failure", "why": "web_search may return no results or generic; trace shows TOOL_RESULT handling"},
    {"id": "fail_03_retrieval", "question": "What is the secret launch code?", "expect": "RETRIEVAL_FAILURE", "why": "RAG has no such document; trace shows retrieval_mode but 0 chunks, planner falls back to parametric"},
    {"id": "fail_04_memory_empty", "question": "What is my favorite color?", "expect": "MEMORY_READ empty", "why": "no memory stored; trace shows MEMORY_READ 0 chars, answer says not specified"},
    {"id": "fail_05_max_steps", "question": "Find population of Japan, China, India, USA and calculate their total", "expect": "MAX_TOOL_STEPS circuit breaker", "why": "needs 5+ tool calls; MAX_TOOL_STEPS=5 should bound it"},
]

def answer_for_trace(tid):
    evs = load_trace(tid)
    for e in reversed(evs):
        if e.get("event_type") == "FINAL_ANSWER":
            return e.get("metadata", {}).get("answer_preview", "")[:120]
    return ""

def main():
    app = create_runnable_graph()
    print("Running 5 intentional failure cases — checking trace diagnosis\n")
    results = []
    for c in CASES:
        print(f"--- {c['id']}: {c['question']!r}")
        out = app.invoke({"question": c["question"]})
        tid = out.get("trace_id")
        evs = out.get("trace_events") or []
        ans = (out.get("answer") or "")[:150]
        print(f"  Answer: {ans!r}")
        print(f"  Trace: {tid}  events={len(evs)}")
        # diagnosis checklist per spec
        checks = {
            "routing_correct": any(e.get("event_type")=="ROUTER" for e in evs),
            "retrieval_correct": any(e.get("event_type")=="RETRIEVAL" for e in evs),
            "planner_decided": any(e.get("event_type")=="PLANNER" for e in evs),
            "tool_selected": any(e.get("event_type")=="TOOL_CALL" for e in evs),
            "tool_args": any("arguments" in str(e.get("metadata",{})) for e in evs if e.get("event_type")=="TOOL_CALL"),
            "tool_succeeded": any(e.get("event_type")=="TOOL_RESULT" and e.get("status")=="success" for e in evs),
            "planner_used_result": any(e.get("event_type")=="PLANNER" and e.get("metadata",{}).get("planner_step",0)>1 for e in evs),
            "why_terminated": out.get("execution_status") or evs[-1].get("event_type") if evs else "?",
            "latencies": out.get("latency_breakdown"),
        }
        for k, v in checks.items():
            print(f"    {k:20}: {v}")
        # root cause from trace
        errs = [e for e in evs if e.get("error")]
        if errs:
            print(f"  Errors:")
            for e in errs:
                err = e.get("error")
                print(f"    {e.get('event_type')} {e.get('node')} {err.get('error_type')}: {err.get('message')[:80]}")
        else:
            print(f"  No explicit errors — check FAILURE taxonomy via planner/tool events")
        print(f"  Inspect: python scripts/inspect_trace.py --trace-id {tid}\n")
        results.append({"id": c["id"], "question": c["question"], "trace_id": tid, "answer_preview": ans, "checks": checks, "error_events": len(errs)})

    out_path = Path("evaluation/results/phase5_failures.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
