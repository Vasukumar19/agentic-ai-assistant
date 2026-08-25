#!/usr/bin/env python
"""
Phase 6B.1 Efficiency Audit — canonical normalization, sequence metrics, repeated/unnecessary analysis.
"""

import json
import pathlib
from collections import Counter

# load benchmark
bench_path = pathlib.Path("evaluation/results/phase6b_real_mcp_benchmark.json")
data = json.loads(bench_path.read_text(encoding="utf-8"))
cases = data["cases"]

# load registry for canonical mapping (if available)
try:
    from mcp_layer.registry import registry
    # ensure discovered
    if not registry._discovered:
        registry.discover()
    def canonicalize(name: str) -> str:
        # if name is alias with underscore, map to dot canonical if exists
        if name in registry._normalized:
            norm = registry.get_normalized(name)
            # alias has same server but different name; canonical is the dot version
            # for underscore aliases, original_name is same, but server is same
            # we can derive canonical as server.original
            orig = norm.original_name
            srv = norm.server
            if srv and norm.name != f"{srv}.{orig}":
                # this is alias, return canonical
                return f"{srv}.{orig}"
            return norm.name
        # fallback: try to convert first underscore to dot and check
        if "_" in name and "." not in name:
            cand = name.replace("_", ".", 1)
            if cand in registry._normalized:
                return cand
        # try underscore->dot for any part
        if "." not in name and "_" in name:
            # e.g., filesystem_list_directory -> filesystem.list_directory
            parts = name.split("_", 1)
            cand = f"{parts[0]}.{parts[1]}"
            if cand in registry._normalized:
                return cand
        return name
except Exception as e:
    print(f"registry not available: {e}")
    def canonicalize(name: str) -> str:
        # fallback simple: filesystem_read_file -> filesystem.read_file
        if "_" in name and "." not in name:
            # split first underscore
            if name.startswith("filesystem_"):
                return name.replace("filesystem_", "filesystem.", 1)
            if name.startswith("test_"):
                return name.replace("test_", "test.", 1)
        return name

# analyze each case
audit = []
total_expected = 0
total_actual = 0
total_extra = 0
repeated_cases = 0
total_repeated_calls = 0

for c in cases:
    raw = c.get("called_tools") or []
    # expected from original CASES in benchmark script — need to load from file or use c's exp if available
    # Our benchmark stored called_tools but not expected; we need to reconstruct expected from id
    # Use mapping from benchmark script
    exp_map = {
        "real_01": ["filesystem.list_directory"],
        "real_02": ["filesystem.read_file"],
        "real_03": ["filesystem.read_file"],
        "real_04": ["filesystem.get_file_info"],
        "real_05": ["filesystem.list_allowed_directories"],
        "real_06": ["filesystem.read_file", "calculator"],
        "real_07": ["filesystem.read_file", "calculator"],
        "real_08": ["filesystem.read_file", "calculator"],
        "real_09": ["calculator", "filesystem.write_file"],
        "real_10": ["filesystem.list_directory", "calculator"],
        "real_11": ["filesystem.read_file"],
        "real_12": ["filesystem.list_directory", "filesystem.read_file"],
        "real_13": ["filesystem.read_file"],
        "real_14": ["filesystem.read_file"],
        "real_15": ["filesystem.list_directory", "calculator"],
        "real_16": ["filesystem.write_file"],
        "real_17": ["filesystem.write_file"],
        "real_18": ["filesystem.write_file", "filesystem.read_file"],
        "real_19": ["filesystem.read_file"],
        "real_20": ["filesystem.read_file"],
        "real_21": ["filesystem.read_file"],
        "real_22": ["filesystem.read_file"],
        "real_23": ["filesystem.list_directory"],
        "real_24": ["filesystem.write_file"],
        "real_25": ["filesystem.read_file", "calculator"],
        "real_26": ["filesystem.list_directory", "filesystem.read_file", "calculator"],
        "real_27": ["filesystem.read_file"],
        "real_28": ["filesystem.get_file_info"],
        "real_29": ["filesystem.list_directory", "filesystem.read_file"],
        "real_30": ["filesystem.write_file"],
    }
    exp = exp_map.get(c["id"], [])
    canonical = [canonicalize(x) for x in raw]
    # metrics
    # exact sequence: raw == exp
    exact = raw == exp
    # canonical sequence: canonical == exp
    canon_exact = canonical == exp
    # acceptable: if exp is subset of canonical in order? For now, same as canon_exact or if canonical starts with exp
    # For Phase 3, acceptable means any declared acceptable sequence; here we have only one exp, so acceptable = canon_exact
    acceptable = canon_exact
    # repeated detection: consecutive or non-consecutive same canonical
    seen = {}
    repeated = 0
    for i, tool in enumerate(canonical):
        if canonical.count(tool) > 1:
            # count duplicates beyond first
            pass
    # count repeated calls: number of times a tool appears more than once
    counter = Counter(canonical)
    repeated_calls = sum(cnt - 1 for cnt in counter.values() if cnt > 1)
    # extra calls: actual - expected, but handle alias normalization
    # For extra, compare canonical vs exp
    # If canonical has more tools than exp, extra = len(canonical) - len(exp) if exp is prefix
    # More precise: extra = max(0, len(canonical) - len(exp)) if not exact, but need to handle missing/extra
    missing = []
    extra = []
    # simple: if canonical == exp -> no missing/extra
    # else: find missing (in exp not in canonical) and extra (in canonical not in exp or extra occurrences)
    if not canon_exact:
        # count missing: tools in exp not in canonical at all
        for e in exp:
            if e not in canonical:
                missing.append(e)
        # extra: tools in canonical not in exp or extra duplicates
        # For duplicates, we already counted repeated
        for tool in set(canonical):
            exp_cnt = exp.count(tool)
            can_cnt = canonical.count(tool)
            if can_cnt > exp_cnt:
                extra.extend([tool] * (can_cnt - exp_cnt))
        # also tools that are in canonical but not in exp at all
        for tool in canonical:
            if tool not in exp and tool not in extra:
                # already counted via above? need to ensure
                pass
        # Handle non-mcp extra like duplicate list_directory
        # For cases where canonical has extra list_directory, it's counted
    else:
        missing = []
        extra = []

    # For cases where canonical has correct tools but extra duplicate, extra will be counted
    # For real_05: exp [list_allowed], canonical [list_allowed, list_allowed, list_allowed] -> extra 2
    # For real_10: exp [list_directory, calculator], canonical [list_directory, calculator, list_directory] -> extra 1 (list_directory)
    # For real_24: exp [write_file], canonical [write_file, write_file] -> extra 1

    audit.append({
        "id": c["id"],
        "expected_sequence": exp,
        "raw_sequence": raw,
        "canonical_sequence": canonical,
        "selection_ok": c.get("selection_ok"),
        "argument_ok": c.get("arg_ok"),
        "success": c.get("success"),
        "exact_sequence": exact,
        "acceptable_sequence": acceptable,
        "canonical_exact": canon_exact,
        "repeated_calls": repeated_calls,
        "extra_calls": len(extra),
        "missing_calls": missing,
        "extra_tools": extra,
        "wrong_order": False,  # for now, assume order is correct if not missing/extra
        "latency_ms": c.get("latency_ms"),
    })
    total_expected += len(exp)
    total_actual += len(canonical)
    total_extra += len(extra)
    if repeated_calls > 0:
        repeated_cases += 1
        total_repeated_calls += repeated_calls

# overall metrics
total_cases = len(cases)
exact_count = sum(1 for a in audit if a["exact_sequence"])
canon_count = sum(1 for a in audit if a["canonical_exact"])
acceptable_count = canon_count  # same
repeated_rate = repeated_cases / total_cases if total_cases else 0

print(f"Exact sequence: {exact_count}/{total_cases} ({exact_count/total_cases*100:.1f}%)")
print(f"Canonical exact: {canon_count}/{total_cases} ({canon_count/total_cases*100:.1f}%)")
print(f"Repeated cases: {repeated_cases}/{total_cases} ({repeated_rate*100:.1f}%)")
print(f"Total repeated calls: {total_repeated_calls}")
print(f"Expected total calls: {total_expected}")
print(f"Actual total calls: {total_actual}")
print(f"Extra calls total: {total_extra}")
print(f"Avg expected per task: {total_expected/total_cases:.2f}")
print(f"Avg actual per task: {total_actual/total_cases:.2f}")
print(f"Avg extra per task: {total_extra/total_cases:.2f}")
if total_actual:
    print(f"Efficiency: {total_expected/total_actual:.3f}")

# latency correlation: normal vs extra-call cases
normal_lats = [a["latency_ms"] for a in audit if a["extra_calls"] == 0]
extra_lats = [a["latency_ms"] for a in audit if a["extra_calls"] > 0]
import statistics
def stats(arr):
    if not arr:
        return {}
    arr_sorted = sorted(arr)
    return {"mean": statistics.mean(arr), "p50": arr_sorted[len(arr_sorted)//2], "p95": arr_sorted[int(len(arr_sorted)*0.95)] if len(arr_sorted)>=5 else max(arr_sorted), "n": len(arr)}
print(f"Normal latency (no extra): {stats(normal_lats)}")
print(f"Extra latency (with extra): {stats(extra_lats)}")

# per-case details
for a in audit:
    if a["extra_calls"] > 0 or not a["canonical_exact"]:
        print(f"{a['id']}: exp {a['expected_sequence']} -> canon {a['canonical_sequence']} extra {a['extra_tools']} missing {a['missing_calls']} latency {a['latency_ms']}")

# save
import json as _json
out_path = pathlib.Path("evaluation/results/phase6b_efficiency_audit.json")
out_path.write_text(_json.dumps(audit, indent=2), encoding="utf-8")
print(f"\nSaved: {out_path}")

# also save summary
summary = {
    "exact_sequence_accuracy": round(exact_count/total_cases*100,1),
    "canonical_sequence_accuracy": round(canon_count/total_cases*100,1),
    "acceptable_sequence_accuracy": round(acceptable_count/total_cases*100,1),
    "repeated_tool_rate": round(repeated_rate*100,1),
    "repeated_cases": repeated_cases,
    "total_repeated_calls": total_repeated_calls,
    "expected_calls_per_task": round(total_expected/total_cases,2),
    "actual_calls_per_task": round(total_actual/total_cases,2),
    "extra_calls_per_task": round(total_extra/total_cases,2),
    "efficiency": round(total_expected/total_actual,3) if total_actual else None,
    "normal_latency": stats(normal_lats),
    "extra_latency": stats(extra_lats),
}
print("\nSummary:", _json.dumps(summary, indent=2))
