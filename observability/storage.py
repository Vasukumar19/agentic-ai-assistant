"""Trace storage — JSONL per day under evaluation/traces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import PROJECT_ROOT

TRACE_DIR = PROJECT_ROOT / "evaluation" / "traces"


def _trace_file_for(date_str: Optional[str] = None) -> Path:
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    return TRACE_DIR / f"{date_str}.jsonl"


def _json_default(o):
    # numpy types, float32 etc.
    try:
        import numpy as np
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    # fallback
    if isinstance(o, (bytes, bytearray)):
        return o.decode("utf-8", errors="replace")
    return str(o)

def persist_trace(state: dict, date_str: Optional[str] = None) -> Optional[Path]:
    """Append all trace_events from state to the daily JSONL file. Returns file path."""
    events = state.get("trace_events") or []
    if not events:
        return None
    fpath = _trace_file_for(date_str)
    with open(fpath, "a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False, default=_json_default) + "\n")
    return fpath


def load_trace(trace_id: str, trace_dir: Optional[Path] = None) -> list[dict]:
    """Scan all daily JSONL files and return events matching trace_id (ordered)."""
    d = trace_dir or TRACE_DIR
    if not d.exists():
        return []
    out: list[dict] = []
    for p in sorted(d.glob("*.jsonl")):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("trace_id") == trace_id:
                    out.append(ev)
        except OSError:
            continue
    out.sort(key=lambda e: e.get("step", 0))
    return out


def query_traces(limit: int = 20, trace_dir: Optional[Path] = None) -> list[dict]:
    """Return most recent REQUEST events (one per trace)."""
    d = trace_dir or TRACE_DIR
    if not d.exists():
        return []
    seen: dict[str, dict] = {}
    for p in sorted(d.glob("*.jsonl"), reverse=True):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                ev = json.loads(line) if line.strip() else None
                if not ev:
                    continue
                if ev.get("event_type") == "REQUEST" and ev.get("trace_id") not in seen:
                    seen[ev["trace_id"]] = ev
                    if len(seen) >= limit:
                        return list(seen.values())
        except OSError:
            continue
    return list(seen.values())
