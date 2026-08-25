"""
Local Qwen3 evaluation: tool matrix, multi-step combos, latency, hardware.

Measures ONLY what the phase3/phase3b benchmarks don't already capture:
1. Direct tool execution latency (mean/P95) per tool
2. Single-tool selection probes through the full graph
3. All supported multi-step combinations with exact sequence accuracy
4. Latency breakdown (planner LLM vs tools vs total)
5. Tokens/sec from Ollama + GPU/RAM snapshot
"""

import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from graph import create_runnable_graph
from nodes.tools import run_tool


def pct(vals, p):
    s = sorted(vals)
    return s[min(len(s) - 1, int(len(s) * p))]


# ── 1. Direct tool execution benchmark ───────────────────────────────────────
def bench_tools():
    print("\n=== 1. DIRECT TOOL EXECUTION ===")
    calc_exprs = ["128 / 8", "25 * 40", "850 * 0.15", "144 ** 0.5", "1024 / 8",
                  "3000 - 450", "(1200 * 12) / 100", "987654 / 12345", "2 ** 16", "77 * 31"]
    ws_queries = ["current population of Japan", "current CEO of Tesla",
                  "price of gold per ounce", "speed of light km/s",
                  "population of Brazil", "height of Mount Everest"]
    rows = {}
    for name, inputs in (("calculator", calc_exprs), ("web_search", ws_queries)):
        lats, ok = [], 0
        for inp in inputs:
            arg = {"expression": inp} if name == "calculator" else {"query": inp}
            t0 = time.perf_counter()
            out = run_tool(name, arg)
            dt = time.perf_counter() - t0
            lats.append(dt)
            good = not str(out).startswith("Error")
            ok += bool(good)
            print(f"  {name}({str(inp)[:40]}) -> {dt:.2f}s ok={good}")
        rows[name] = {
            "n": len(inputs),
            "success_rate": ok / len(inputs),
            "mean_s": statistics.mean(lats),
            "p50_s": statistics.median(lats),
            "p95_s": pct(lats, 0.95),
            "max_s": max(lats),
        }
        print(f"  {name}: success={ok}/{len(inputs)} mean={rows[name]['mean_s']:.2f}s p95={rows[name]['p95_s']:.2f}s")
    return rows


# ── 2+3. Graph probes ────────────────────────────────────────────────────────
SELECTION_PROBES = [
    {"id": "sel_calc", "query": "What is 15% of 240?", "expected": ["calculator"]},
    {"id": "sel_ws", "query": "Who is the current CEO of Nvidia?", "expected": ["web_search"]},
    {"id": "sel_rag", "query": "What is our security protocol for password rotation according to company documents?", "expected": ["rag"]},
    {"id": "sel_direct", "query": "Explain what a binary search algorithm is.", "expected": []},
]

COMBO_PROBES = [
    {"id": "combo_web_calc", "query": "Search for the population of Germany and calculate 2% of it.",
     "expected": ["web_search", "calculator"]},
    {"id": "combo_rag_calc", "query": "According to our training budget policy document, what is the annual training budget per employee? Calculate the total for 4 employees.",
     "expected": ["rag", "calculator"]},
    {"id": "combo_web_web", "query": "Find the population of France and also the population of Spain.",
     "expected": ["web_search", "web_search"]},
    {"id": "combo_rag_web", "query": "Which frontend framework does our internal tech stack doc say we use, and what is its latest major version according to the web?",
     "expected": ["rag", "web_search"]},
    {"id": "combo_mem_calc", "query": "My monthly salary is 4000 dollars according to what I told you before. Calculate my yearly salary by multiplying by 12.",
     "expected": ["memory_search", "calculator"]},
]


def _run_graph(app, case):
    t0 = time.perf_counter()
    state = app.invoke({"question": case["query"]})
    total = time.perf_counter() - t0

    trace = state.get("execution_trace", [])
    plan = state.get("retrieval_plan", {})
    completed = list(state.get("completed_steps", []))
    tool_results = list(state.get("tool_results", []))

    actual = []
    if plan.get("rag"):
        actual.append("rag")
    if plan.get("profile") or plan.get("semantic"):
        actual.append("memory_search")
    # ordered tool executions from trace (authoritative order)
    for tr in trace:
        if tr.get("action") == "tool" and tr.get("tool"):
            actual.append(tr["tool"])
    if not any(tr.get("action") == "tool" for tr in trace):
        # fall back to completed_steps minus pre-retrieval entries
        for step in completed:
            if step not in ("rag", "memory_search"):
                actual.append(step)

    planner_calls = sum(1 for tr in trace if str(tr.get("step", "")).startswith("planner"))
    planner_time = sum(tr.get("llm_latency_s", 0) for tr in trace if "llm_latency_s" in tr)

    return {
        "actual": actual,
        "status": state.get("execution_status"),
        "answer": state.get("answer", ""),
        "planner_calls": planner_calls,
        "planner_llm_time_s": round(planner_time, 2),
        "tool_calls": len(tool_results),
        "total_s": round(total, 2),
        "arg_trace": [{"tool": r["tool"], "args": r["arguments"]} for r in tool_results],
    }


def run_probes(app):
    print("\n=== 2. SELECTION PROBES ===")
    sel_rows = []
    for c in SELECTION_PROBES:
        r = _run_graph(app, c)
        ok = r["actual"] == c["expected"]
        sel_rows.append({**c, **r, "pass": ok})
        print(f"  [{c['id']}] exp={c['expected']} act={r['actual']} {'PASS' if ok else 'FAIL'} ({r['total_s']}s)")

    print("\n=== 3. MULTI-STEP COMBOS ===")
    combo_rows = []
    for c in COMBO_PROBES:
        r = _run_graph(app, c)
        exact = r["actual"] == c["expected"]
        prefix_ok = r["actual"][:len(c["expected"])] == c["expected"]
        combo_rows.append({**c, **r, "exact_match": exact})
        print(f"  [{c['id']}] exp={c['expected']} act={r['actual']} "
              f"{'EXACT' if exact else ('prefix-ok' if prefix_ok else 'MISMATCH')} ({r['total_s']}s)")
    return sel_rows, combo_rows


# ── 4. Tokens/sec from raw Ollama API ────────────────────────────────────────
def tokens_per_sec():
    import urllib.request
    body = json.dumps({"model": "qwen3:8b", "prompt": "Write a 50-word summary of what a hash map is.",
                       "stream": False}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    wall = time.perf_counter() - t0
    ec = data.get("eval_count", 0)
    dur = data.get("eval_duration", 1) / 1e9
    return {
        "wall_s": round(wall, 2),
        "eval_tokens": ec,
        "model_tok_s": round(ec / dur, 1) if dur else None,
        "effective_wall_tok_s": round(ec / wall, 1) if wall else None,
        "load_duration_s": round(data.get("load_duration", 0) / 1e9, 3),
        "prompt_eval_count": data.get("prompt_eval_count"),
    }


def hardware_snapshot():
    snap = {}
    try:
        q = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        name, used, total, util = q.stdout.strip().split(", ")
        snap["gpu"] = {"name": name, "vram_used_mb": int(used), "vram_total_mb": int(total),
                       "util_pct": int(util)}
    except Exception as e:
        snap["gpu"] = f"N/A ({e.__class__.__name__})"
    try:
        import psutil
        vm = psutil.virtual_memory()
        snap["ram_gb"] = {"used": round(vm.used / 1e9, 1), "total": round(vm.total / 1e9, 1)}
    except Exception:
        snap["ram_gb"] = "N/A"
    return snap


def main():
    app = create_runnable_graph()

    # Warm the model so cold-load doesn't pollute first probe
    app.invoke({"question": "hi"})

    tool_bench = bench_tools()
    sel_rows, combo_rows = run_probes(app)

    print("\n=== 4. TOKENS/SEC ===")
    tps = tokens_per_sec()
    print(f"  {tps}")

    print("\n=== 5. HARDWARE SNAPSHOT (under no load) ===")
    hw = hardware_snapshot()
    print(f"  {hw}")

    out = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool_execution_bench": tool_bench,
        "selection_probes": sel_rows,
        "multistep_combos": combo_rows,
        "tokens_per_sec": tps,
        "hardware_snapshot": hw,
    }
    path = Path("evaluation/results/qwen3_local_eval.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2)
    print(f"\nSaved: {path}")

    exact = sum(r["exact_match"] for r in combo_rows)
    print(f"\nCombo exact-sequence accuracy: {exact}/{len(combo_rows)}")


if __name__ == "__main__":
    main()
