#!/usr/bin/env python
"""Phase 7 — evaluate baseline vs dependency vs replan on identical dataset."""

import json
import statistics
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


def evaluate(results_file: str, strategy: str):
    raw = json.loads(Path(results_file).read_text(encoding="utf-8"))
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
        premature = status == "running"  # ended while still mid-plan
        loop = status == "repeated_tool_call"

        completed = status == "completed"
        audit.append({
            "id": r["id"], "category": r["category"], "executed": True,
            "server_ok": server_ok, "tool_ok": tool_ok,
            "exact_sequence": exact, "acceptable_sequence": acceptable,
            "deps_expected": deps_total, "deps_met": deps_met,
            "repeated_calls": repeated,
            "extra_calls": max(0, len(called) - len(exp_set)),
            "premature_termination": premature, "tool_loop": loop,
            "awaiting_confirmation": r.get("awaiting_confirmation", False),
            "completed": completed,
            "latency_ms": r["latency_ms"], "llm_calls": r.get("llm_calls", 0),
            "status": status,
        })
        if not premature and not loop and completed:
            (lat_extra if repeated > 0 or len(called) > len(exp_set) else lat_normal).append(r["latency_ms"])
        elif r["latency_ms"]:
            lat_extra.append(r["latency_ms"])

    done = [a for a in audit if a["executed"]]
    n = len(done)

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
            "avg_tools": round(sum(len([1]) * 0 + 0 for g in grp), 0),
        }

    lats = [a["latency_ms"] for a in done]
    llm = [a["llm_calls"] for a in done]

    return {
        "strategy": strategy,
        "n": n,
        "server_selection_pct": rate("server_ok"),
        "tool_selection_pct": rate("tool_ok"),
        "dependency_accuracy": round(deps_ok / deps_all * 100, 1) if deps_all else None,
        "dependency_edges": f"{deps_ok}/{deps_all}",
        "exact_sequence_pct": rate("exact_sequence"),
        "acceptable_sequence_pct": rate("acceptable_sequence"),
        "task_completion_pct": rate("completed"),
        "premature_termination_pct": rate(None, lambda a: a["premature_termination"]),
        "tool_loop_rate_pct": rate(None, lambda a: a["tool_loop"]),
        "cases_with_repeats": sum(1 for a in done if a["repeated_calls"] > 0),
        "total_repeated_calls": sum(a["repeated_calls"] for a in done),
        "tool_efficiency": round(sum(len(a.get("expected_sequence", [])) for a in done) /
                                  max(1, sum(a["extra_calls"] + len(a.get("expected_sequence", [])) - 0 for a in done)), 3),
        "latency": {"mean": round(statistics.mean(lats), 1) if lats else None,
                     "p50": round(pct(lats, 50), 1), "p95": round(pct(lats, 95), 1)},
        "latency_normal": stats(lat_normal), "latency_extra": stats(lat_extra),
        "avg_llm_calls_per_query": round(statistics.mean(llm), 2) if llm else None,
        "by_service_count": scale,
    }


def stats(arr):
    arr = arr or []
    if not arr:
        return {}
    return {"mean": round(statistics.mean(arr), 1), "p50": round(pct(arr, 50), 1), "p95": round(pct(arr, 95), 1), "n": len(arr)}


def main():
    base_dir = Path("evaluation/results")
    out = {}
    for strategy, fname in [("baseline", "phase7_baseline_phase6c.json"),
                             ("dependency", "phase7_dependency_results.json"),
                             ("replan", "phase7_replan_results.json")]:
        p = base_dir / fname
        if not p.exists():
            print(f"missing {fname}, skipping")
            continue
        res = evaluate(str(p), strategy)
        out[strategy] = res
        print(json.dumps(res, indent=2))
    out_path = base_dir / "phase7_strategy_comparison.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
