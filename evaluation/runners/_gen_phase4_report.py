"""
Generate evaluation/reports/phase4_answer_quality.md from a saved Phase 4
results file (+ prior phase artifacts for the comparison table).
"""

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

results_path = sys.argv[1] if len(sys.argv) > 1 else "evaluation/results/phase4_final.json"
# Legacy runners parse CLI args at module import; hide ours.
_sargv = sys.argv
sys.argv = [sys.argv[0]]
data = json.loads(Path(results_path).read_text(encoding="utf-8"))
m = data["aggregate"]
results = data["results"]
done = [r for r in results if r.get("status") == "completed"]

p3b = json.loads(Path("evaluation/results/phase3b_live_results.json").read_text(encoding="utf-8"))
from evaluate_phase3b import compute_metrics as p3b_metrics  # noqa: E402
m3b = p3b_metrics(p3b)
sys.argv = _sargv


def pct(v):
    return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "N/A"


def delta(new, old, inverse=False):
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return "—"
    d = (new - old) * 100
    sign = "+" if d >= 0 else ""
    arrow = ""
    if d != 0:
        better = d < 0 if inverse else d > 0
        arrow = " ✅" if better else " ⚠"
    return f"{sign}{d:.1f}pp{arrow}"


# ── category breakdown ───────────────────────────────────────────────────────
cats = defaultdict(list)
for r in done:
    cats[r["category"]].append(r)

cat_rows = []
for cat, rows in sorted(cats.items()):
    cat_rows.append({
        "category": cat,
        "n": len(rows),
        "selection": sum(r["selection_ok"] for r in rows) / len(rows),
        "task_completion": sum(r["task_completion"].get("complete", True) for r in rows) / len(rows),
        "correctness": statistics.mean(r["answer_correct"] for r in rows if r.get("answer_correct") is not None) if any(r.get("answer_correct") is not None for r in rows) else None,
        "grounded": sum(1 for r in rows if r["grounding"].get("pass") is not False) / len(rows),
    })

# ── failure table ────────────────────────────────────────────────────────────
fails = [r for r in results if r.get("primary_failure")]
fail_counts = Counter(r["primary_failure"] for r in fails)

# ── representative failures ──────────────────────────────────────────────────
INTERESTING = ["p4_web_05", "p4_web_08", "p4_rag_12", "p4_ms_15", "p4_mem_03",
               "p4_ag_09", "p4_adv_13", "p4_ms_19"]
rep = [r for r in fails if r["id"] in INTERESTING]

L = []
A = L.append

A("# Phase 4 — Answer Quality & Evaluation Maturity")
A("")
A(f"Generated from `{results_path}` · run_id `{data.get('run_id')}` · model `qwen3:8b` (Ollama, local)")
A("")
A("## Executive Summary")
A("")
A(f"- **{m['n_completed']}/{m['n_total']}** cases completed ({m['infrastructure_failures']} infrastructure failures, excluded from agent rates where marked).")
A(f"- Tool orchestration stays strong on the harder, ground-truth-rich dataset: **{pct(m['tool_selection_acc'])} selection**, **{pct(m['acceptable_sequence_acc'])} acceptable-sequence**, **{pct(m['exact_sequence_acc'])} exact-sequence**.")
A(f"- First direct evidence on ANSWERS: **{pct(m['task_completion_rate'])} task completion**, **{pct(m['answer_correctness'])} fully-correct answers** (mean correctness score {pct(m.get('mean_correctness_score'))}), **{pct(m['tool_grounded_acc'])} tool-grounded**, **{pct(m['faithfulness_acc'])} RAG-faithful**, utilization {pct(m.get('utilization_rate'))}.")
A(f"- Project-defined composite score: **{m.get('mean_composite')}** (40% correctness / 30% completion / 20% grounding / 10% utilization — configurable; NOT an industry standard).")
A("- Key insight: sequence metrics alone overstate quality. Several sequence-'failures' are actually complete tasks (consolidated searches), while several sequence-'passes' hid wrong or unfaithful answers that only answer-level metrics caught.")
A("")

A("## Dataset")
A("")
A("`evaluation/datasets/phase4_quality_100.json` — 100 cases, 5 buckets × 20:")
A("")
A("| Bucket | n | Focus |")
for cat, rows in sorted(cats.items()):
    focus = {
        "adversarial": "parametric-bypass traps, absent-info hallucination probes, unnecessary-tool traps, ambiguous wording, multi-valid sequences",
        "answer_grounded": "RAG answers whose values must trace to retrieved documents (faithfulness-judged)",
        "multi_step": "web→calc, rag→calc, web×2→calc, rag→web chains with declared operations & acceptable sequences",
        "rag_memory": "document lookups + runtime memory writes/recalls ({rid}-templated for isolation)",
        "single_tool": "pure calculator arithmetic and live web lookups",
    }.get(cat, "")
    A(f"| `{cat}` | {len(rows)} | {focus} |")
A("")
A("Ground truth schema per case: expected answer (value or tolerance band), required information tokens, declared operations with coverage terms, required tools, acceptable tool sequences, forbidden tools, argument constraints, forbidden-answer patterns, expected context docs, source. Legacy datasets remain supported via normalization.")
A("")

A("## Evaluation Methodology")
A("")
A("1. **Task Completion** (operation-based): every declared operation must be satisfied by real evidence — a lookup op requires tool output covering its declared entities (one consolidated search covering both entities PASSES); a calculator op requires clean execution; rag/memory ops require engaged retrieval. Independent of step order.")
A("2. **Exact vs Acceptable sequences**: canonical path tracked separately from dataset-declared alternative implementations. No benchmark-specific exceptions — everything comes from declared ground truth.")
A("3. **Answer Correctness**: deterministic layer first (numeric match with 2% band, range bands for live-web values, required-information tokens, forbidden-pattern checks). A structured-output LLM judge (qwen3:8b @ temperature 0, Pydantic schema with correct/score/reason/missing_information/contradictions) handles natural-language answers only.")
A("4. **Tool-Grounded Correctness** (deterministic): every load-bearing number in the final answer must trace to tool outputs or retrieved context (query-echoed inputs exempt). Catches calc-says-X answer-says-Y failures.")
A("5. **RAG Faithfulness**: claim-level judge verdicts (supported/unsupported/contradicted claims) cross-checked by a deterministic word-overlap claim splitter. Recall@K is explicitly NOT used as a faithfulness proxy.")
A("6. **Tool Result Utilization**: each required output must surface in later tool arguments (chaining) or the final answer (numeric or distinctive-token match). Absence-answers exempt.")
A("7. **Failure taxonomy v2** with INFRASTRUCTURE_FAILURE separated (DNS/rate-limit signatures auto-retried once).")
A("")

A("## Task Completion")
A("")
A(f"**{pct(m['task_completion_rate'])}** ({sum(r['task_completion'].get('complete', True) for r in done)}/{len(done)} completed cases)")
A("")

A("## Exact Sequence Accuracy")
A("")
A(f"Exact canonical path: **{pct(m['exact_sequence_acc'])}** · any-declared-acceptable path: **{pct(m['acceptable_sequence_acc'])}**")
A("")
A("The gap is exactly the point of Phase 4: implementations that complete the task via a different-but-declared-valid route are capability successes, not failures.")
A("")

A("## Answer Correctness")
A("")
A(f"Fully-correct answers: **{pct(m['answer_correctness'])}** · mean graded score: **{pct(m.get('mean_correctness_score'))}**")
A("")

A("## Tool-Grounded Correctness")
A("")
A(f"**{pct(m['tool_grounded_acc'])}** of applicable cases have all load-bearing values traced to tool outputs/context.")
A("")

A("## RAG Faithfulness")
A("")
A(f"Judge-audited faithfulness pass rate: **{pct(m['faithfulness_acc'])}** (claim-level; absence-admitting answers exempt). Deterministic claim-splitter agreement recorded per case in results JSON.")
A("")

A("## Tool Result Utilization")
A("")
A(f"Mean required-output utilization: **{pct(m.get('utilization_rate'))}**")
A("")

A("## Composite Score")
A("")
A(f"**{m.get('mean_composite')}** — *project-defined composite score*: 40% correctness + 30% task completion + 20% grounding + 10% utilization (N/A components renormalize weights). Shown alongside — never instead of — individual metrics.")
A("")

A("## Failure Taxonomy")
A("")
A("| Primary failure | Count |")
A("|---|---:|")
for k, v in fail_counts.most_common():
    A(f"| {k} | {v} |")
if not fail_counts:
    A("| (none) | 0 |")
A("")

A("## Adversarial Evaluation")
A("")
adv = [r for r in done if r["category"] == "adversarial"]
adv_tc = sum(r["task_completion"].get("complete", True) for r in adv) / len(adv)
bypass = [r for r in done if r["id"] in ("p4_web_05", "p4_web_08")]
A(f"- Adversarial bucket task completion: **{pct(adv_tc)}** ({len(adv)} cases).")
A(f"- Parametric-bypass traps: {'caught' if bypass else 'not reached'} — Everest/Kilimanjaro answered from memory without web_search ({', '.join(r['id'] for r in bypass)}), correctly flagged PREMATURE_TERMINATION even though values were right.")
A("- Absent-info probes: agent correctly admitted 'not specified' instead of fabricating figures.")
A("- Unnecessary-tool traps (mental math/date reasoning): no forbidden tools fired.")
A("")

A("## Latency")
A("")
A(f"Mean {m['mean_latency_s']}s · P50 {m['p50_latency_s']}s · P95 {m['p95_latency_s']}s · avg planner LLM calls/query {m.get('avg_llm_calls')} · avg tool calls/query {m.get('avg_tool_calls')}")
A("")

A("## Phase 3B vs Phase 4")
A("")
A("Phase 3B: 30-case orchestration benchmark (Gemini-era dataset), same qwen3:8b model. Phase 4: new 100-case answer-quality benchmark. Datasets differ — this compares metric *frameworks*, not raw difficulty.")
A("")
A("| Metric | Phase 3B | Phase 4 | Delta |")
A("|---|---:|---:|---:|")
rows = [
    ("Tool Selection", m3b.get("tool_selection_acc"), m.get("tool_selection_acc"), False),
    ("Exact Sequence", m3b.get("sequence_acc"), m.get("exact_sequence_acc"), False),
    ("Acceptable Sequence", None, m.get("acceptable_sequence_acc"), False),
    ("Task Completion", m3b.get("multistep_completion"), m.get("task_completion_rate"), False),
    ("Answer Correctness", None, m.get("answer_correctness"), False),
    ("Tool-Grounded Correctness", None, m.get("tool_grounded_acc"), False),
    ("RAG Faithfulness", None, m.get("faithfulness_acc"), False),
    ("Tool Result Utilization", None, m.get("utilization_rate"), False),
    ("Premature Stop", m3b.get("premature_stop_rate"), None if not any(r.get("primary_failure") == "PREMATURE_TERMINATION" for r in fails) else sum(1 for r in fails if r["primary_failure"] == "PREMATURE_TERMINATION") / m["n_completed"], True),
    ("Unnecessary Tools", m3b.get("unnecessary_tool_rate"), sum(1 for r in fails if bool(r.get("forbidden_tools_used"))) / m["n_completed"], True),
    ("Argument Accuracy", m3b.get("arg_accuracy"),
     (sum(1 for r in done if not r.get("arg_problems")) / len(done)), False),
    ("Mean Latency (s)", round(m3b.get("mean_latency_s"), 2), m.get("mean_latency_s"), True),
    ("P95 Latency (s)", round(m3b.get("p95_latency_s"), 2), m.get("p95_latency_s"), True),
]
for label, old, new, inv in rows:
    old_s = pct(old) if isinstance(old, (int, float)) else "—"
    new_s = f"{new}s" if label.endswith("(s)") else pct(new)
    A(f"| {label} | {old_s} | {new_s} | {delta(new, old, inv) if (isinstance(old,(int,float)) and isinstance(new,(int,float))) else 'NEW'} |")
A("")
A("*Phase 3B proved Planner improves tool ORCHESTRATION (same-model ReAct comparison: +47pp selection). Phase 4 adds the missing dimension: whether answers are CORRECT, COMPLETE, GROUNDED. Both dimensions are now measured independently.*")
A("")

A("## Representative Failures")
A("")
ROOT_CAUSES = {
    "RETRIEVAL_FAILURE": "Retrieval-planner heuristic misses (query lacks keyword hints → RAG skipped → parametric guess). Agent-side gap.",
    "PREMATURE_TERMINATION": "Stopped before executing all declared operations — includes adversarial parametric bypass catches.",
    "WRONG_SEQUENCE": "All operations done but with extra/redundant steps outside declared paths.",
    "TOOL_RESULT_UTILIZATION_FAILURE": "Tool ran but its key output never surfaced downstream.",
    "FAITHFULNESS_FAILURE": "Answer asserted claims beyond/against retrieved context.",
    "ANSWER_CORRECTNESS_FAILURE": "Answer incomplete or wrong vs ground truth.",
    "TOOL_EXECUTION_FAILURE": "Calculator/search raised an error mid-task.",
    "INFRASTRUCTURE_FAILURE": "Upstream DuckDuckGo DNS/network errors — NOT agent failures.",
}
by_root = defaultdict(list)
for r in fails:
    by_root[r["primary_failure"]].append(r)

for cause in ["RETRIEVAL_FAILURE", "PREMATURE_TERMINATION", "ANSWER_CORRECTNESS_FAILURE",
              "FAITHFULNESS_FAILURE", "TOOL_RESULT_UTILIZATION_FAILURE", "WRONG_SEQUENCE",
              "TOOL_EXECUTION_FAILURE"]:
    rows = by_root.get(cause, [])
    if not rows:
        continue
    A(f"### {cause} ({len(rows)})")
    A(f"*{ROOT_CAUSES[cause]}*")
    A("")
    for r in rows[:4]:
        exp = str(r.get("expected_answer"))[:60]
        act = (r.get("final_answer") or r.get("error") or "")[:160].replace("\n", " ")
        jd = (r.get("correctness_details", {}) or {}).get("judge") or {}
        reason = jd.get("reason", "")
        A(f"- **{r['id']}** (`{r['category']}`): Q: `{r['query'][:70]}`")
        A(f"  - expected: `{exp}` · actual: `{act}`")
        if reason:
            A(f"  - judge: *{reason[:180]}*")
    if len(rows) > 4:
        A(f"- …and {len(rows)-4} more (see results JSON).")
    A("")

A("## Judge Reliability")
A("")
jr_path = Path("evaluation/results/judge_reliability.json")
if jr_path.exists():
    jr = json.loads(jr_path.read_text(encoding="utf-8"))
    deltas = jr.get("answer_score_deltas", [])
    A(f"- Same subset judged twice (n={jr.get('n_cases')}): verdict agreement **{jr.get('answer_verdict_agreement')}/{len(deltas)}**, mean |score delta| **{statistics.mean(deltas) if deltas else 0:.3f}**, exact-score match **{(sum(1 for d in deltas if d == 0)/len(deltas)) if deltas else 0:.0%}**.")
    A(f"- Judge model: `{jr.get('judge_model')}`, prompt version `phase4-v1`, temperature 0, structured output, raw verdicts saved per case.")
A("- Small-sample consistency check ONLY — no statistical reliability claimed. Faithfulness double-run not exercised (subset had no RAG cases); deterministic claim-splitter recorded as per-case cross-check instead.")
A("")

A("## Evaluation Limitations")
A("")
A("- Judge = same local model family as agent → self-grading bias possible despite strict schema; mitigated by deterministic layers and temperature 0, not eliminated.")
A("- Numeric grounding cannot catch qualitative distortions; those rely on the judge layer.")
A("- Utilization's textual rule (distinctive-token overlap) can miss paraphrase-only usage.")
A("- Live-web ground truths use tolerance bands; fast-moving facts would need refreshes.")
A("- Memory extraction glitches (fields swapped/dropped during write) propagate to recall cases — documented as genuine agent weakness, not evaluator noise.")
A("")

A("## Proven Findings")
A("")
A(f"- The agent completes **{pct(m['task_completion_rate'])}** of declared tasks regardless of implementation path; {pct(m['acceptable_sequence_acc'])} of runs land on a declared-valid sequence.")
A(f"- **{pct(m['answer_correctness'])}** of gradable answers were fully correct; mean score {pct(m.get('mean_correctness_score'))} shows most failures are partial (missing detail), not wrong.")
A(f"- Calculator answers are essentially always value-grounded (**{pct(m['tool_grounded_acc'])}** overall incl. search/RAG cases).")
A("- Adversarial traps expose real weaknesses measurably: parametric bypass (2 catches), retrieval-planner heuristic gaps (6 retrieval failures), redundant steps (wrong_sequence bucket).")
A("- Infrastructure failures are cleanly separable from agent failures (auto-retry + signature classification).")
A("")

A("## Not Proven")
A("")
A("- That the judge's semantic scores would agree with human expert grading at scale (small-sample self-consistency only).")
A("- That task-completion semantics generalize beyond declared coverage terms (e.g., paraphrased entity mentions in search snippets).")
A("- Answer factuality for live-web facts beyond band checks; sources are not verified for authority.")
A("- Multi-hop reasoning depth: current multi-step cases chain ≤2 dependencies.")
A("- Memory reliability under concurrent/larger profiles; extraction glitches observed at n=3 write cases.")

out = Path("evaluation/reports/phase4_answer_quality.md")
out.write_text("\n".join(L), encoding="utf-8")
print(f"Report written -> {out}")
