"""
Judge reliability: run the structured judge TWICE over saved phase-4
results and measure agreement — both answer correctness AND RAG faithfulness
(using the rag_context_excerpt persisted per case).

Agreement metrics:
- verdict agreement (same boolean)
- mean |score delta|
- exact score match rate

Small-sample consistency check, NOT a statistical reliability claim.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

results_path = sys.argv[1] if len(sys.argv) > 1 else "evaluation/results/phase4_final.json"
subset_n = int(sys.argv[2]) if len(sys.argv) > 2 else 12

from evaluation.metrics.judge import AnswerJudge

data = json.loads(Path(results_path).read_text(encoding="utf-8"))
done = [r for r in data["results"] if r.get("status") == "completed"]

# split subsets: answers need expected_answer; faithfulness needs stored context
ans_pool = [r for r in done if r.get("expected_answer") is not None][:subset_n]
faith_pool = [r for r in done if r.get("rag_context_excerpt")][:subset_n]

judge = AnswerJudge()

ans_match, ans_deltas = 0, []
for r in ans_pool:
    try:
        v1 = judge.judge_answer(r["query"], r["expected_answer"], r["final_answer"],
                                evidence=r.get("rag_context_excerpt", ""))["verdict"]
        v2 = judge.judge_answer(r["query"], r["expected_answer"], r["final_answer"],
                                evidence=r.get("rag_context_excerpt", ""))["verdict"]
        if v1["correct"] == v2["correct"]:
            ans_match += 1
        ans_deltas.append(abs(v1["score"] - v2["score"]))
    except Exception as exc:
        print(f"  [{r['id']}] answer judge error: {str(exc)[:100]}")

f_match, f_deltas = 0, []
for r in faith_pool:
    ctx = r.get("rag_context_excerpt", "")
    try:
        f1 = judge.judge_faithfulness(r["query"], ctx, r["final_answer"])["verdict"]
        f2 = judge.judge_faithfulness(r["query"], ctx, r["final_answer"])["verdict"]
        d = abs(f1["faithfulness_score"] - f2["faithfulness_score"])
        f_deltas.append(d)
        if d < 0.01 and (f1["contradictions"] == f2["contradictions"]):
            f_match += 1
    except Exception as exc:
        print(f"  [{r['id']}] faith judge error: {str(exc)[:100]}")

print("\n── Judge Reliability ──")
if ans_deltas:
    print(f"  ANSWER  : agreement {ans_match}/{len(ans_deltas)} "
          f"({(ans_match / len(ans_deltas) * 100):.0f}%) · "
          f"mean |Δscore| {statistics.mean(ans_deltas):.3f} · "
          f"exact-match {(sum(1 for d in ans_deltas if d == 0) / len(ans_deltas)):.0%}")
else:
    print("  ANSWER  : no cases judged")
if f_deltas:
    print(f"  FAITH   : agreement {f_match}/{len(f_deltas)} "
          f"({(f_match / len(f_deltas) * 100):.0f}%) · "
          f"mean |Δscore| {statistics.mean(f_deltas):.3f}")
else:
    print("  FAITH   : no RAG-context cases available")
print(f"  judge model: {judge.model_name}")
print("NOTE: small-sample consistency check only — not a statistical claim.")

Path("evaluation/results/judge_reliability.json").write_text(json.dumps({
    "answer_cases": len(ans_deltas),
    "answer_verdict_agreement": ans_match,
    "answer_score_deltas": ans_deltas,
    "faith_cases": len(f_deltas),
    "faith_agreement": f_match,
    "faith_score_deltas": f_deltas,
    "judge_model": judge.model_name,
}, indent=2), encoding="utf-8")
