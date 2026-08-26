#!/usr/bin/env python
"""Phase 7B — evaluate hybrid (+ablations) against Phase 7 strategies on identical dataset."""

import json
import statistics
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.runners.phase7_evaluate import evaluate  # reuse identical scoring


CONFIGS = [
    ("baseline", "phase7_baseline_phase6c.json"),
    ("dependency", "phase7_dependency_results.json"),
    ("replan", "phase7_replan_results.json"),
    ("hybrid", "phase7_hybrid_cap2_rep1_results.json"),
    ("hybrid_noreplan", "phase7_hybrid_cap2_rep0_results.json"),
    ("hybrid_baseonly", "phase7_hybrid_cap0_rep1_results.json"),
]


def main():
    out = {}
    for name, fname in CONFIGS:
        p = Path("evaluation/results") / fname
        if not p.exists():
            print(f"missing {fname}")
            continue
        res = evaluate(str(p), name)
        # fix efficiency calc: expected/actual tool calls
        done = [c for c in json.loads(p.read_text(encoding="utf-8"))["cases"] if "error" not in c]
        exp_total = sum(len(c.get("expected_tools") or []) for c in done)
        act_total = sum(len(c.get("called_raw") or []) for c in done)
        res["expected_calls_per_task"] = round(exp_total / max(len(done), 1), 2)
        res["actual_calls_per_task"] = round(act_total / max(len(done), 1), 2)
        res["tool_call_efficiency"] = round(exp_total / act_total, 3) if act_total else None
        repeats = sum(1 for r in done if len((r.get("called_raw") or [])) != len(set(r.get("called_raw") or [])))
        rep_calls = 0
        for r in done:
            cnt = {}
            for t in (r.get("called_raw") or []):
                cnt[t] = cnt.get(t, 0) + 1
            rep_calls += sum(v - 1 for v in cnt.values() if v > 1)
        res["cases_with_repeats"] = repeats
        res["total_repeated_calls"] = rep_calls
        out[name] = res

    out_path = Path("evaluation/results/phase7b_strategy_comparison.json")
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'Strategy':<18}{'Sel%':>7}{'Deps%':>7}{'Exact%':>8}{'Compl%':>8}{'Prem%':>7}{'Loop%':>7}{'Eff':>7}{'Mean':>9}{'P95':>9}{'LLM/q':>7}")
    for name, v in out.items():
        print(f"{name:<18}{v['tool_selection_pct']:>7}{str(v['dependency_accuracy']):>7}"
              f"{v['exact_sequence_pct']:>8}{v['task_completion_pct']:>8}"
              f"{v['premature_termination_pct']:>7}{v['tool_loop_rate_pct']:>7}"
              f"{str(v.get('tool_call_efficiency')):>7}{v['latency']['mean']:>9}{v['latency']['p95']:>9}"
              f"{str(v.get('avg_llm_calls_per_query')):>7}")
    print("\nBy service count:")
    for name, v in out.items():
        sc = v.get("by_service_count", {})
        row = " | ".join(f"{k}-svc: sel {g['tool_selection_pct']}% dep {g['dependency_pct']}% compl {g['completion_pct']}%"
                         for k, g in sc.items())
        print(f"  {name:<18}{row}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
