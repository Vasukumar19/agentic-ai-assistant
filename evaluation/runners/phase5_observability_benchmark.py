#!/usr/bin/env python
"""
Phase 5 observability benchmark — 20 real Qwen3 requests via Ollama.
"""

import json
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen3:8b")
os.environ.setdefault("OLLAMA_REASONING", "0")

from graph import create_runnable_graph

CASES = [
    {"id": "obs_01_chat", "question": "hello", "category": "direct_answer"},
    {"id": "obs_02_calc", "question": "What is 12 * 7?", "category": "calculator"},
    {"id": "obs_03_calc2", "question": "calculate 128 / 8", "category": "calculator"},
    {"id": "obs_04_web", "question": "What is the population of Japan?", "category": "web_search"},
    {"id": "obs_05_web2", "question": "What is the height of Mount Everest in meters?", "category": "web_search"},
    {"id": "obs_06_rag", "question": "What is GlobalTech's PTO policy?", "category": "RAG"},
    {"id": "obs_07_rag2", "question": "What database does GlobalTech use as primary?", "category": "RAG"},
    {"id": "obs_08_mem_write", "question": "Remember that my name is Ada.", "category": "memory_write"},
    {"id": "obs_09_mem_read", "question": "What is my name?", "category": "memory_read"},
    {"id": "obs_10_mem_update", "question": "Remember that my favorite programming language is Rust.", "category": "memory_update"},
    {"id": "obs_11_web_calc", "question": "Find the population of Japan and calculate 0.5% of it.", "category": "web_search_calc"},
    {"id": "obs_12_rag_calc", "question": "Our policy grants 20 PTO days per year. If I take 5 days off, how many are left?", "category": "rag_calc"},
    {"id": "obs_13_multi2", "question": "Find the populations of Norway and Sweden and tell me their total combined population.", "category": "multi_step"},
    {"id": "obs_14_invalid_args", "question": "calculate 5% of 100000000", "category": "invalid_args"},
    {"id": "obs_15_premature", "question": "How tall is Mount Everest? Don't search, just answer.", "category": "premature"},
    {"id": "obs_16_retry", "question": "What is the current price of Bitcoin?", "category": "web_search"},
    {"id": "obs_17_repeated_tool", "question": "calculate 2+2 and then calculate 2+2 again with same args", "category": "repeated"},
    {"id": "obs_18_rag_grounded", "question": "What percentage of health insurance premiums does GlobalTech cover?", "category": "RAG"},
    {"id": "obs_19_adversarial", "question": "Per our sales playbook, who approves discounts up to 15%?", "category": "adversarial"},
    {"id": "obs_20_complex", "question": "What is the annual professional development budget per employee? What would it be for a team of 5?", "category": "rag_calc"},
]

def pct(data, p):
    if not data:
        return None
    s = sorted(data)
    k = (len(s)-1) * p / 100
    f = int(k)
    c = int(k) + 1
    if c >= len(s):
        return s[-1]
    d0 = k - f
    return s[f] * (1-d0) + s[c] * d0

def main():
    app = create_runnable_graph()
    results = []
    all_latencies = []
    planner_lats = []
    tool_lats = []
    retrieval_lats = []
    traces = []
    print(f"Running {len(CASES)} observability benchmark cases via Qwen3:8b (Ollama)...\n")
    for i, case in enumerate(CASES, 1):
        q = case["question"]
        cid = case["id"]
        cat = case["category"]
        print(f"[{i}/{len(CASES)}] {cid} ({cat}): {q[:50]!r} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            out = app.invoke({"question": q})
            dur_ms = int((time.perf_counter() - t0) * 1000)
            ans = (out.get("answer") or "")[:120]
            tid = out.get("trace_id")
            evs = out.get("trace_events") or []
            lb = out.get("latency_breakdown") or {}
            all_latencies.append(dur_ms)
            if lb.get("planner"):
                planner_lats.append(lb["planner"])
            tool_sum = sum(v for k, v in lb.items() if k.startswith("tool:"))
            if tool_sum:
                tool_lats.append(tool_sum)
            ret_sum = lb.get("retrieval_planner", 0) + lb.get("rag_retriever", 0) + lb.get("memory_retriever", 0)
            if ret_sum:
                retrieval_lats.append(ret_sum)
            traces.append(tid)
            results.append({"id": cid, "category": cat, "question": q, "answer_preview": ans,
                            "trace_id": tid, "latency_ms": dur_ms, "events": len(evs),
                            "latency_breakdown": lb, "status": out.get("execution_status", "completed")})
            print(f"-> {dur_ms}ms events={len(evs)} trace={str(tid)[:12]}...")
        except Exception as exc:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            print(f"ERROR {exc!r}")
            results.append({"id": cid, "category": cat, "question": q, "error": str(exc)[:300], "latency_ms": dur_ms})
    def stats(arr):
        if not arr:
            return {}
        return {"mean": round(statistics.mean(arr),1), "p50": round(pct(arr,50),1) if len(arr)>=2 else arr[0],
                "p95": round(pct(arr,95),1) if len(arr)>=5 else max(arr),
                "p99": round(pct(arr,99),1) if len(arr)>=10 else max(arr),
                "max": max(arr), "min": min(arr), "n": len(arr)}
    summary = {
        "total_latency_ms": stats(all_latencies),
        "planner_latency_ms": stats(planner_lats),
        "tool_latency_ms": stats(tool_lats),
        "retrieval_latency_ms": stats(retrieval_lats),
    }
    print("\n" + "="*70)
    print("Latency breakdown (ms):")
    for k, v in summary.items():
        print(f"  {k:25} {v}")
    print(f"\nTraces: {traces[:5]} ...")
    out_path = Path("evaluation/results/phase5_observability.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"cases": results, "summary": summary, "traces": traces}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")
    if traces:
        print(f"\nInspect example: python scripts/inspect_trace.py --trace-id {traces[0]}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
