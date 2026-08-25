"""
Regenerate a benchmark report from an existing (possibly retry-merged)
results JSON without re-running any case.

Usage:
  python _regen_report.py --results evaluation/results/phase3b_live_results.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

args = sys.argv[1:]
assert "--results" in args, "usage: --results <path>"
results_path = args[args.index("--results") + 1]

# evaluate_phase3b/live parse CLI args at module import; neutralize during import.
sys.argv = [sys.argv[0]]
if "phase3b" in results_path:
    import evaluate_phase3b as mod
    REPORT = mod.REPORT_PATH

    def gen(results):
        return mod.generate_report(
            results, is_mock=False,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
elif "phase3_live" in results_path:
    import evaluate_phase3_live as mod
    REPORT = mod.REPORT_PATH

    def gen(results):
        return mod.generate_report(
            results, None,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
else:
    raise SystemExit("Unknown results file")
sys.argv = [sys.argv[0]]

results = json.load(open(results_path, encoding="utf-8"))
Path(REPORT).write_text(gen(results), encoding="utf-8")

print(f"Report: {REPORT}")
m = mod.compute_metrics(results)
for k, v in m.items():
    if isinstance(v, float) and ("acc" in k or "rate" in k or "completion" in k):
        print(f"  {k}: {v*100:.1f}%")
    else:
        print(f"  {k}: {v if not isinstance(v, float) else round(v, 3)}")
