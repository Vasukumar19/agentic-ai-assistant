"""Request / Trace ID generation."""

import uuid
from datetime import datetime, timezone


def new_request_id() -> str:
    return f"req_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex}"


def ensure_trace_ids(state: dict) -> dict:
    """Ensure state has request_id and trace_id; generate if missing. Returns update dict."""
    out = {}
    if not state.get("request_id"):
        out["request_id"] = new_request_id()
    if not state.get("trace_id"):
        out["trace_id"] = new_trace_id()
    if "trace_events" not in state or state.get("trace_events") is None:
        out["trace_events"] = []
    if "trace_step" not in state or state.get("trace_step") is None:
        out["trace_step"] = 0
    if "latency_breakdown" not in state or state.get("latency_breakdown") is None:
        out["latency_breakdown"] = {}
    if "tool_failure_counts" not in state or state.get("tool_failure_counts") is None:
        out["tool_failure_counts"] = {}
    return out
