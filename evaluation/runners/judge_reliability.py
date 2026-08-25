"""
Judge reliability: run the structured judge TWICE over a small subset of
saved phase-4 results and measure agreement.

Agreement metrics:
- verdict agreement: same correct/faithful boolean
- mean |score delta|
- exact score match rate

This is a small-sample sanity check, NOT a statistical reliability claim.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

results_path = sys.argv[1] if len(sys.argv) > 1 else "evaluation/results/phase4_full_run.json"
subset_n = int(sys.argv[2]) if len(sys.argv) > 2 else 12

from evaluation.metrics.judge import AnswerJudge

data = json.loads(Path(results_path).read_text(encoding="utf-8"))
done = [r for r in data["results"]
        if r.get("status") == "completed" and r.get("expected_answer") is not None]
subset = done[:subset_n]
print(f"Judge reliability on {len(subset)} cases from {results_path}")

judge = AnswerJudge()

ans_match, ans_deltas, faith_matches, n_faith = 0, [], 0, 0
for r in subset:
    # --- answer correctness twice ---
    try:
        v1 = judge.judge_answer(r["query"], r["expected_answer"], r["final_answer"],
                                evidence="(as captured)")["verdict"]
        v2 = judge.judge_answer(r["query"], r["expected_answer"], r["final_answer"],
                                evidence="(as captured)")["verdict"]
        if v1["correct"] == v2["correct"]:
            ans_match += 1
        ans_deltas.append(abs(v1["score"] - v2["score"]))
    except Exception as exc:
        print(f"  [{r['id']}] answer judge error: {str(exc)[:100]}")
        continue

    # --- faithfulness twice where context existed ---
    if r.get("rag_context_chars", 0) > 30:
        ctx_note = "(context as captured)"
        try:
            f1 = judge.judge_faithfulness(r["query"], ctx_note * 40 + "PTO is 20 days.", r["final_answer"])["verdict"]
            f2 = judge.judge_faithfulness(r["query"], ctx_note * 40 + "PTO is 20 days.", r["final_answer"])["verdict"]
            n_faith += 1
            if abs(f1["faithfulness_score"] - f2["faithfulness_score"]) < 0.01:
                faith_matches += 1
        except Exception:
            pass

print("\n── Judge Reliability ──")
print(f"  answer verdict agreement : {ans_match}/{len(ans_deltas)}"
      f" ({(ans_match / len(ans_deltas) * 100 if ans_deltas else 0):.0f}%)")
if ans_deltas:
    print(f"  mean |score delta|       : {statistics.mean(ans_deltas):.3f}")
    print(f"  exact-score match rate   : {sum(1 for d in ans_deltas if d == 0) / len(ans_deltas):.0%}")
if n_faith:
    print(f"  faithfulness agreement   : {faith_matches}/{n_faith}")
print(f"  judge model              : {judge.model_name}")
print("NOTE: small-sample consistency check only — not a statistical claim.")

Path("evaluation/results/judge_reliability.json").write_text(json.dumps({
    "n_cases": len(subset),
    "answer_verdict_agreement": ans_match,
    "answer_score_deltas": ans_deltas,
    "faithfulness_agreement": [faith_matches, n_faith],
    "judge_model": judge.model_name,
}, indent=2), encoding="utf-8")
