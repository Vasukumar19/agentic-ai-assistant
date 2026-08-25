"""
Web ground-truth band refresh check
====================================

Phase 4 web-search cases carry expected_answer_range bands captured on
2026-08-25. Live facts drift. This tool re-checks each range case against
CURRENT search results and reports whether present-day evidence still falls
inside the declared band.

Read-only by default (report). Use --apply to widen/update bands from the
fresh evidence (changes are written back to the dataset and should be
reviewed via git diff before committing).
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("--dataset", default="evaluation/datasets/phase4_quality_100.json")
parser.add_argument("--apply", action="store_true",
                    help="write refreshed bands back to the dataset")
args = parser.parse_args()

from nodes.tools import run_tool

NUM_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*")


def extract_numbers(text):
    out = []
    for tok in NUM_RE.findall(text or ""):
        t = tok.replace("$", "").replace(",", "").rstrip("%")
        try:
            v = float(t)
            out.append(int(v) if v == int(v) else v)
        except ValueError:
            pass
    return out


dataset_path = Path(args.dataset)
cases = json.loads(dataset_path.read_text(encoding="utf-8"))
range_cases = [c for c in cases if c.get("expected_answer_range")]

print(f"{len(range_cases)} range-carrying web case(s) — checking against live search\n")

changed = []
for c in range_cases:
    lo, hi = c["expected_answer_range"]
    out = run_tool("web_search", {"query": c["query"]})
    nums = extract_numbers(str(out))
    in_band = [n for n in nums if lo <= n <= hi]
    # nearest number outside band, for a suggested widened band
    outside = [n for n in nums if not (lo <= n <= hi)]
    near = min(outside, key=lambda n: min(abs(n - lo), abs(n - hi))) if outside else None

    status = "OK" if in_band else "DRIFT?"
    suggestion = ""
    if not in_band and near is not None:
        new_lo, new_hi = sorted([lo, min([hi, near], key=lambda x: abs(x - ((lo + hi) / 2)))] )
        # propose a band centered on fresh evidence with 5% padding
        pad = abs(near) * 0.05
        suggestion = f"suggested band: [{int((near - pad) // 1)}, {int((near + pad) // 1)}] (evidence={near})"

    print(f"[{status}] {c['id']}: band=[{lo}, {hi}] | {len(in_band)} in-band value(s)")
    if status != "OK":
        print(f"        {suggestion}")
        if args.apply and near is not None:
            pad = abs(near) * 0.05
            c["expected_answer_range"] = [int(near - pad), int(near + pad)]
            c["band_refreshed"] = str(date.today())
            changed.append(c["id"])
    time.sleep(1.0)

if args.apply and changed:
    dataset_path.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(f"\nApplied updates to {len(changed)} case(s): {changed}")
    print("Review with git diff before committing.")
else:
    print("\nReport-only run (use --apply to update drifted bands).")
