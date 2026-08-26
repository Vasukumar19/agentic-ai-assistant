#!/usr/bin/env python
"""Evaluate a budget benchmark result file.

Usage: python evaluation/runners/budget_evaluate.py evaluation/results/phase8_hybrid_budget7_results.json
"""

import json
import statistics
import sys
from pathlib import Path


def pct(data, p):
    if not data:
        return None
    s = sorted(data)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = int(k) + 1
    return s[-1] if c >= len(s) else s[f] * (1 - (k - f)) + s[c] * (k - f)


def canon(name: str) -> str:
    for srv in ("calendar", "notes", "reminders"):
        prefix = srv + "_"
        if name.startswith(prefix) and "." not in name:
            return srv + "." + name[len(prefix):]
    return name


def evaluate(results_file: str):
    raw = json.loads(Path(results_file).read_text(encoding="utf-8"))
    budget = raw.get("budget", "?")
    cases = raw["cases"]
    audit, lat_normal, lat_extra = [], [], []

    for r in cases:
        if "error" in r:
            audit.append({"id": r["id"], "executed": False, "primary_failure": "INFRASTRUCTURE_FAILURE"})
            continue
        exp_set = set(r.get("expected_tools") or [])
        called = [canon(t) for t in (r.get("called_raw") or [])]
        call_set = set(called)
        called_servers = {t.split(".")[0] if "." in t else t.split("_")[0] for t in called}
        exp_servers = set(r.get("expected_servers") or [])
        server_ok = exp_servers.issubset(called_servers) if exp_servers else True
        tool_ok = exp_set.issubset(call_set) if exp_set else True
        exact = called == (r.get("expected_tools") or [])
        variants = [[canon(t) for t in v] for v in r.get("acceptable_variants", [])]
        acceptable = exact or called in variants

        deps_total = len(r.get("expected_dependencies") or [])
        deps_met = 0
        for a, b in (r.get("expected_dependencies") or []):
            if a in called and b in called and called.index(a) < called.index(b):
                deps_met += 1

        counter = {}
        for t in called:
            counter[t] = counter.get(t, 0) + 1
        repeated = sum(c - 1 for c in counter.values() if c > 1)

        status = r.get("execution_status")
        premature = status == "running"
        loop = status == "repeated_tool_call"
        budget_exhausted = status == "budget_exhausted"
        completed = status == "completed"

        audit.append({
            "id": r["id"], "category": r["category"], "executed": True,
            "server_ok": server_ok, "tool_ok": tool_ok,
            "exact_sequence": exact, "acceptable_sequence": acceptable,
            "deps_expected": deps_total, "deps_met": deps_met,
            "repeated_calls": repeated,
            "extra_calls": max(0, len(called) - len(exp_set)),
            "premature_termination": premature, "tool_loop": loop,
            "budget_exhausted": budget_exhausted,
            "awaiting_confirmation": r.get("awaiting_confirmation", False),
            "completed": completed,
            "latency_ms": r["latency_ms"], "llm_calls": r.get("llm_calls", 0),
            "status": status,
        })
        if not premature and not loop and not budget_exhausted and completed:
            (lat_extra if repeated > 0 or len(called) > len(exp_set) else lat_normal).append(r["latency_ms"])
        elif r["latency_ms"]:
            lat_extra.append(r["latency_ms"])

    done = [a for a in audit if a["executed"]]
    n = len(done)
    infra_fail = len([a for a in audit if not a["executed"]])

    def rate(key, pred=None):
        vals = [a[key] if pred is None else pred(a) for a in done]
        vals = [v for v in vals if isinstance(v, bool)]
        return round(sum(vals) / len(vals) * 100, 1) if vals else None

    deps_all = sum(a["deps_expected"] for a in done)
    deps_ok = sum(a["deps_met"] for a in done)

    by_srv = {"1": [a for a in done if a["category"] == "single_server"],
              "2": [a for a in done if a["category"] in ("calendar_notes", "calendar_reminders", "notes_reminders")],
              "3": [a for a in done if a["category"] == "three_server"]}
    scale = {}
    for k, grp in by_srv.items():
        if not grp:
            continue
        d_tot = sum(g["deps_expected"] for g in grp)
        d_met = sum(g["deps_met"] for g in grp)
        scale[k] = {
            "n": len(grp),
            "tool_selection_pct": round(sum(g["tool_ok"] for g in grp) / len(grp) * 100, 1),
            "dependency_pct": round(d_met / d_tot * 100, 1) if d_tot else None,
            "completion_pct": round(sum(g["completed"] for g in grp) / len(grp) * 100, 1),
            "mean_latency_ms": round(statistics.mean([g["latency_ms"] for g in grp]), 1),
        }

    lats = [a["latency_ms"] for a in done]
    llm = [a["llm_calls"] for a in done]

    total_repeated = sum(a["repeated_calls"] for a in done)
    cases_with_repeats = sum(1 for a in done if a["repeated_calls"] > 0)

    summary = {
        "budget": budget,
        "n": n,
        "infra_failures": infra_fail,
        "server_selection_pct": rate("server_ok"),
        "tool_selection_pct": rate("tool_ok"),
        "dependency_accuracy": round(deps_ok / deps_all * 100, 1) if deps_all else None,
        "dependency_edges": f"{deps_ok}/{deps_all}",
        "exact_sequence_pct": rate("exact_sequence"),
        "acceptable_sequence_pct": rate("acceptable_sequence"),
        "task_completion_pct": rate("completed"),
        "premature_termination_pct": rate("premature_termination"),
        "tool_loop_rate_pct": rate("tool_loop"),
        "budget_exhaustion_pct": rate("budget_exhausted"),
        "cases_with_repeats": cases_with_repeats,
        "total_repeated_calls": total_repeated,
        "expected_calls_per_task": round(sum(len(r.get("expected_tools") or []) for r in cases) / max(len(cases), 1), 2),
        "actual_calls_per_task": round(sum(len(r.get("called_raw") or []) for r in cases) / max(n, 1), 2),
        "latency": {
            "mean": round(statistics.mean(lats), 1) if lats else None,
            "p50": round(pct(lats, 50), 1) if lats else None,
            "p95": round(pct(lats, 95), 1) if lats else None,
        },
        "avg_llm_calls_per_query": round(sum(llm) / max(len(llm), 1), 2),
        "by_service_count": scale,
    }
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: budget_evaluate.py <results.json>")
        raise SystemExit(1)
    s = evaluate(sys.argv[1])
    print(json.dumps(s, indent=2))
