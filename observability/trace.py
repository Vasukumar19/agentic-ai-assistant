"""Structured execution events — TraceEvent schema and helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# canonical event types
EVENT_TYPES = [
    "REQUEST",
    "ROUTER",
    "CONTEXT_BUILD",
    "QUERY_REWRITE",
    "RETRIEVAL",
    "PLANNER",
    "TOOL_CALL",
    "TOOL_RESULT",
    "MEMORY_READ",
    "MEMORY_WRITE",
    "FINAL_ANSWER",
    "ERROR",
    "RETRY",
    "TIMEOUT",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    trace_id: str
    request_id: str
    timestamp: str
    event_type: str
    node: str
    step: int
    duration_ms: Optional[int] = None
    status: str = "success"  # success | error | retry | timeout
    metadata: dict = field(default_factory=dict)
    error: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # keep json-serializable — asdict already does it
        return d


def make_event(
    state: dict,
    event_type: str,
    node: str,
    duration_ms: Optional[int] = None,
    status: str = "success",
    metadata: Optional[dict] = None,
    error: Optional[dict] = None,
) -> dict:
    """Build an event dict and bump trace_step. Returns event dict (caller should append)."""
    trace_id = state.get("trace_id", "trace_unknown")
    request_id = state.get("request_id", "req_unknown")
    step = state.get("trace_step", 0) + 1
    state["trace_step"] = step
    ev = TraceEvent(
        trace_id=trace_id,
        request_id=request_id,
        timestamp=utc_now_iso(),
        event_type=event_type,
        node=node,
        step=step,
        duration_ms=duration_ms,
        status=status,
        metadata=metadata or {},
        error=error,
    )
    return ev.to_dict()


def append_event(state: dict, event: dict) -> None:
    """Append event to state trace_events list (creates list if needed)."""
    if "trace_events" not in state or state["trace_events"] is None:
        state["trace_events"] = []
    state["trace_events"].append(event)


def add_latency(state: dict, component: str, duration_ms: int) -> None:
    """Accumulate latency per component."""
    if "latency_breakdown" not in state or state["latency_breakdown"] is None:
        state["latency_breakdown"] = {}
    cur = state["latency_breakdown"].get(component, 0)
    state["latency_breakdown"][component] = cur + duration_ms


def extract_llm_usage(response, latency_ms: int | None = None) -> dict:
    """Extract provider/model/token usage from a LangChain response, without fabricating."""
    meta = getattr(response, "response_metadata", {}) or {}
    usage = getattr(response, "usage_metadata", None)
    # fallback: try meta usage
    if usage is None:
        usage = meta.get("usage") or {}
    # normalize
    if isinstance(usage, dict):
        input_tok = usage.get("input_tokens") or usage.get("prompt_tokens")
        output_tok = usage.get("output_tokens") or usage.get("completion_tokens")
        total_tok = usage.get("total_tokens")
    else:
        # usage_metadata object
        try:
            input_tok = getattr(usage, "input_tokens", None)
            output_tok = getattr(usage, "output_tokens", None)
            total_tok = getattr(usage, "total_tokens", None)
        except Exception:
            input_tok = output_tok = total_tok = None
    # model/provider from meta
    model = meta.get("model") or meta.get("model_name")
    # generation_time if present (Ollama)
    gen_time = meta.get("total_duration") or meta.get("load_duration")
    tps = None
    if total_tok and latency_ms and latency_ms > 0:
        try:
            tps = round(total_tok / (latency_ms / 1000), 2)
        except Exception:
            tps = None
    return {
        "provider": meta.get("provider") or "unknown",
        "model": model,
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "total_tokens": total_tok,
        "latency_ms": latency_ms,
        "tokens_per_second": tps,
        "raw_response_metadata_keys": list(meta.keys())[:10] if meta else [],
    }


def traced(event_type: str, node: str):
    """Decorator for node functions: auto-times, emits event, handles errors."""
    import functools
    import time
    from .ids import ensure_trace_ids
    from .errors import classify_error, make_error_payload

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            ensure = ensure_trace_ids(state)
            for k, v in ensure.items():
                if k not in state or state.get(k) is None:
                    state[k] = v
            t0 = time.perf_counter()
            try:
                result = fn(state)
                dur = int((time.perf_counter() - t0) * 1000)
                add_latency(state, node, dur)
                # emit success event if function didn't already emit
                # we emit a generic event here; detailed nodes may emit richer already
                # avoid double-emitting if fn already handled tracing (check marker)
                if result is not None and isinstance(result, dict) and result.get("_traced"):
                    # fn handled its own tracing
                    out = dict(result)
                    out.pop("_traced", None)
                    return out
                ev = make_event(state, event_type, node, duration_ms=dur, status="success",
                                metadata={"traced": True})
                append_event(state, ev)
                if result is None:
                    return {"trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                            "latency_breakdown": state.get("latency_breakdown")}
                # include trace updates
                if isinstance(result, dict):
                    result = dict(result)
                    result["trace_events"] = state.get("trace_events")
                    result["trace_step"] = state.get("trace_step")
                    result["latency_breakdown"] = state.get("latency_breakdown")
                return result
            except Exception as exc:
                dur = int((time.perf_counter() - t0) * 1000)
                add_latency(state, node, dur)
                err_type = classify_error(exc, component=node)
                err_payload = make_error_payload(err_type, node, str(exc), trace_id=state.get("trace_id"))
                ev = make_event(state, "ERROR", node, duration_ms=dur, status="error",
                                metadata={"exception": type(exc).__name__}, error=err_payload)
                append_event(state, ev)
                # also emit original event_type as error
                ev2 = make_event(state, event_type, node, duration_ms=dur, status="error",
                                 metadata={"error": str(exc)[:300]}, error=err_payload)
                append_event(state, ev2)
                raise
        return wrapper
    return decorator
