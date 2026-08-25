"""Observability package — tracing, error taxonomy, storage, latency."""

from .ids import new_request_id, new_trace_id, ensure_trace_ids
from .trace import TraceEvent, make_event, append_event, utc_now_iso
from .errors import ErrorType, classify_error, make_error_payload
from .storage import persist_trace, load_trace, query_traces
from .redaction import safe_serialize, redact_value

__all__ = [
    "new_request_id", "new_trace_id", "ensure_trace_ids",
    "TraceEvent", "make_event", "append_event", "utc_now_iso",
    "ErrorType", "classify_error", "make_error_payload",
    "persist_trace", "load_trace", "query_traces",
    "safe_serialize", "redact_value",
]
