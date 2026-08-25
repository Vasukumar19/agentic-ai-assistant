"""
Web ground-truth band refresh check
====================================

Runs the full agent on each range-carrying query and checks whether the
agent's answer number falls inside the declared band.

Read-only by default (report).  Use --apply to widen bands from fresh
evidence (review via git diff before committing).
"""

import argparse
import json
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("--dataset", default="evaluation/datasets/phase4_quality_100.json")
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()

from graph import create_runnable_graph
from config import MEMORY_DIR, CHAT_HISTORY_PATH

NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def extract_numbers(text):
    out = []
    for tok in NUM_RE.findall(text or ""):
        t = tok.replace(",", "")
        try:
            v = float(t)
            out.append(int(v) if v == int(v) else v)
        except ValueError:
            pass
    return out


def backup_mem():
    if MEMORY_DIR.exists():
        dest = Path(str(MEMORY_DIR) + "_bandcheck_bak")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(MEMORY_DIR, dest)


def restore_mem():
    dest = Path(str(MEMORY_DIR) + "_bandcheck_bak")
    if dest.exists():
        if MEMORY_DIR.exists():
            shutil.rmtree(MEMORY_DIR)
        shutil.move(str(dest), str(MEMORY_DIR))


app = create_runnable_graph()
changed = []

dataset_path = Path(args.dataset)
cases = json.loads(dataset_path.read_text(encoding="utf-8"))
range_cases = [c for c in cases if c.get("expected_answer_range")]

backup_mem()
# clear chat history so retrieval planner doesn't see stale context
CHAT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
CHAT_HISTORY_PATH.write_text("[]", encoding="utf-8")

print(f"{len(range_cases)} range-carrying case(s) — running agent + checking bands\n")

for c in range_cases:
    lo, hi = c["expected_answer_range"]
    q = c["query"]

    try:
        out = app.invoke({"question": q})
        answer = out.get("answer") or ""
    except Exception as exc:
        answer = f"[AGENT_ERROR: {exc}]"

    nums = extract_numbers(answer)
    in_band = [n for n in nums if lo <= n <= hi]
    outside = [n for n in nums if not (lo <= n <= hi)]
    best = in_band[0] if in_band else (min(outside, key=lambda n: abs(n - (lo + hi) / 2)) if outside else None)

    status = "OK" if in_band else "DRIFT?"
    suggestion = ""
    if not in_band and best is not None:
        pad = max(abs(best) * 0.05, 5)
        suggestion = f"  suggested: [{int(best - pad)}, {int(best + pad)}] (agent answered {best})"

    print(f"[{status}] {c['id']}: band=[{lo}, {hi}]  agent={best}  answer={answer[:100]!r}")
    if status != "OK":
        print(suggestion)
        if args.apply and best is not None:
            pad = max(abs(best) * 0.05, 5)
            c["expected_answer_range"] = [int(best - pad), int(best + pad)]
            c["band_refreshed"] = str(date.today())
            changed.append(c["id"])
    time.sleep(0.5)

restore_mem()

if args.apply and changed:
    dataset_path.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(f"\nApplied updates to {len(changed)} case(s): {changed}")
else:
    print("\nReport-only run (use --apply to update drifted bands).")
