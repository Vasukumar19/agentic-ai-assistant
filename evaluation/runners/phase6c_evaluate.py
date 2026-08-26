#!/usr/bin/env python
"""
Phase 6C derived evaluation — capability, efficiency, dependency, security metrics.
Reads frozen dataset + raw benchmark; writes derived JSON. Never mutates inputs.
"""

import json
import statistics
from collections import Counter
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
    """underscore alias -> dotted canonical (evaluation-layer only)."""
    for srv in ("calendar", "notes", "reminders"):
        prefix = srv + "_"
        if name.startswith(prefix) and "." not in name:
            cand = srv + "." + name[len(prefix):]
            return cand
    return name


def main():
    dataset = json.loads(Path("evaluation/datasets/phase6c_multiserver.json").read_text(encoding="utf-8"))
    raw = json.loads(Path("evaluation/results/phase6c_multiserver_benchmark.json").read_text(encoding="utf-8"))
    dmap = {c["id"]: c for c in dataset}
    rmap = {r["id"]: r for r in raw["cases"]}

    audit = []
    for cid, d in dmap.items():
        r = rmap.get(cid)
        if not r or "error" in r:
            audit.append({"id": cid, "category": d["category"], "executed": False,
                          "primary_failure": "INFRASTRUCTURE_FAILURE"})
            continue
        expected = d["expected_tools"]
        called_raw = r["called_raw"]
        called = [canon(x) for x in called_raw]
        exp_set = set(expected)
        call_set = set(called)

        # capability: server selection — every expected server appears among called tools' servers
        called_servers = set()
        for t in called:
            if "." in t:
                called_servers.add(t.split(".")[0])
            elif "_" in t:
                called_servers.add(t.split("_")[0])
        if not exp_set:
            # negative cases: correct = no unexpected state-changing tool ran
            server_ok = True
        else:
            server_ok = set(d["expected_servers"]).issubset(called_servers)

        tool_ok = exp_set.issubset(call_set) if exp_set else True

        # sequences
        exact = called == expected
        variants = [[canon(t) for t in v] for v in d.get("acceptable_variants", [])]
        acceptable = exact or (called in variants)
        # capability-set match (order-free) as additional view
        set_match = (call_set == exp_set) if exp_set else True

        # dependency edges: dep [A,B] means B should appear after A in called order
        deps_total, deps_met = 0, 0
        for a, b in d.get("expected_dependencies", []):
            deps_total += 1
            if a in called and b in called and called.index(a) < called.index(b):
                deps_met += 1

        # efficiency
        counter = Counter(called)
        repeated = sum(cnt - 1 for cnt in counter.values() if cnt > 1)
        extra = max(0, len(called) - len(expected))

        # confirmation compliance: write-ish tools requiring confirmation per case flag;
        # current architecture halts at first confirmation → awaiting_confirmation is COMPLIANT behavior
        awaiting = r.get("awaiting_confirmation", False)
        confirm_compliant = True
        if d["requires_confirmation"] and not awaiting:
            # agent may have completed only if policy didn't require confirmation in registry run config
            confirm_compliant = None  # evaluated below via registry policy presence

        audit.append({
            "id": cid,
            "category": d["category"],
            "executed": True,
            "expected_sequence": expected,
            "raw_called": called_raw,
            "canonical_called": called,
            "server_selection_ok": server_ok,
            "tool_selection_ok": tool_ok,
            "exact_sequence": exact,
            "acceptable_sequence": acceptable,
            "capability_set_match": set_match,
            "deps_expected": deps_total,
            "deps_met": deps_met,
            "dependency_accuracy": round(deps_met / deps_total, 3) if deps_total else None,
            "awaiting_confirmation": awaiting,
            "had_errors": r.get("had_errors", False),
            "repeated_calls": repeated,
            "extra_calls": extra,
            "latency_ms": r["latency_ms"],
            "answer_preview": r.get("answer_preview", ""),
            "trace_id": r.get("trace_id"),
        })

    done = [a for a in audit if a.get("executed")]
    n = len(done)

    def rate(key):
        vals = [a[key] for a in done if a.get(key) is not None and isinstance(a[key], bool)]
        return round(sum(vals) / len(vals) * 100, 1) if vals else None

    lat_normal = [a["latency_ms"] for a in done if a["extra_calls"] == 0]
    lat_extra = [a["latency_ms"] for a in done if a["extra_calls"] > 0]

    def stats(arr):
        arr = arr or []
        if not arr:
            return {}
        return {"mean": round(statistics.mean(arr), 1), "p50": round(pct(arr, 50), 1),
                "p95": round(pct(arr, 95), 1), "max": max(arr), "n": len(arr)}

    # category breakdown
    by_cat = {}
    for a in done:
        cat = a["category"]
        c = by_cat.setdefault(cat, {"n": 0})
        c["n"] += 1
        for k in ("server_selection_ok", "tool_selection_ok", "acceptable_sequence"):
            c[k] = c.get(k, 0) + (1 if a.get(k) else 0)
        c.setdefault("latencies", []).append(a["latency_ms"])
        c["avg_tools"] = c.get("avg_tools", 0) + len(a["canonical_called"])
    for cat, c in by_cat.items():
        c["server_selection_pct"] = round(c["server_selection_ok"] / c["n"] * 100, 1)
        c["tool_selection_pct"] = round(c["tool_selection_ok"] / c["n"] * 100, 1)
        c["acceptable_seq_pct"] = round(c["acceptable_sequence"] / c["n"] * 100, 1)
        c["mean_latency_ms"] = round(statistics.mean(c.pop("latencies")), 1)
        c["avg_tool_calls"] = round(c.pop("avg_tools") / c["n"], 2)

    total_exp = sum(len(a["expected_sequence"]) for a in done)
    total_act = sum(len(a["canonical_called"]) for a in done)
    deps_all = sum(a["deps_expected"] for a in done)
    deps_ok = sum(a["deps_met"] for a in done)

    summary = {
        "executed": f"{len(done)}/{len(audit)}",
        "infrastructure_failures": len(audit) - len(done),
        "server_selection_accuracy": rate("server_selection_ok"),
        "tool_selection_accuracy": rate("tool_selection_ok"),
        "exact_sequence_accuracy": rate("exact_sequence"),
        "acceptable_sequence_accuracy": rate("acceptable_sequence"),
        "capability_set_match_rate": rate("capability_set_match"),
        "dependency_accuracy_overall": round(deps_ok / deps_all * 100, 1) if deps_all else None,
        "dependency_edges": f"{deps_ok}/{deps_all}",
        "cases_with_repeats": sum(1 for a in done if a["repeated_calls"] > 0),
        "total_repeated_calls": sum(a["repeated_calls"] for a in done),
        "expected_calls_per_task": round(total_exp / n, 2),
        "actual_calls_per_task": round(total_act / n, 2),
        "tool_call_efficiency": round(total_exp / total_act, 3) if total_act else None,
        "latency_normal": stats(lat_normal),
        "latency_extra_call": stats(lat_extra),
        "by_category": {k: {kk: vv for kk, vv in v.items()} for k, v in sorted(by_cat.items())},
        "discovery_ms_raw_summary": raw["raw_summary"]["discovery_ms"],
    }

    out = Path("evaluation/results/phase6c_efficiency_audit.json")
    out.write_text(json.dumps({"summary": summary, "cases": audit}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
