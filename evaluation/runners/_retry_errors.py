"""
Retry only the status='error' cases of a saved benchmark results file.
Infrastructure flakes (DNS/network) should not permanently remove cases
from an otherwise-completed local benchmark. Merges results in place.
"""

import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

results_path = Path(sys.argv[1])
dataset_path = Path(sys.argv[2])

# evaluate_phase3b/live parse args at module level; neutralize for import.
_saved_argv = list(sys.argv)
sys.argv = [sys.argv[0]]
if "phase3b" in results_path.name:
    from evaluate_phase3b import run_case as run_one
else:
    from evaluate_phase3_live import run_case as run_one
sys.argv = _saved_argv

from graph import create_runnable_graph

results = json.load(open(results_path, encoding="utf-8"))
dataset = {c["id"]: c for c in json.load(open(dataset_path, encoding="utf-8"))}
app = create_runnable_graph()

retry_ids = [r["id"] for r in results if r.get("status") == "error"]
print(f"Retrying {len(retry_ids)} errored case(s): {retry_ids}")

for rid in retry_ids:
    case = dataset[rid]
    print(f"[{rid}] {case['query'][:65]}")
    try:
        res = run_one(app, case)
        results = [res if r["id"] == rid else r for r in results]
        print(f"   -> {res['actual_sequence']} {'PASS' if res['sequence_correct'] else res['failure_type']}")
    except Exception as exc:
        print(f"   -> STILL ERRORING: {str(exc)[:120]}")
    time.sleep(1.0)

with open(results_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"Merged into {results_path}")
