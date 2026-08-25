"""Conservative retry policy — only retry transient failures."""

from __future__ import annotations

import time
import logging
from typing import Callable, Any

from .errors import is_retryable, max_retries_for, ErrorType

logger = logging.getLogger(__name__)

# never retry these even if classified as retryable by message
NEVER_RETRY_SUBSTRINGS = [
    "invalid arguments",
    "malformed",
    "pydantic",
    "validation",
    "calculator",  # deterministic errors
    "unknown tool",
]


def should_retry_message(msg: str) -> bool:
    low = (msg or "").lower()
    return not any(s in low for s in NEVER_RETRY_SUBSTRINGS)


def call_with_retry(
    func: Callable[[], Any],
    component: str,
    state: dict,
    max_retries: int | None = None,
    base_delay_s: float = 0.5,
) -> Any:
    """Call func with bounded retries for retryable errors. Emits RETRY events into state."""
    from .trace import make_event, append_event, utc_now_iso
    from .errors import classify_error, make_error_payload

    last_exc: Exception | None = None
    # we don't know error_type until first failure; use max_retries as cap
    cap = max_retries if max_retries is not None else 1
    for attempt in range(cap + 1):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            err_type = classify_error(exc, component=component)
            retryable = is_retryable(err_type) and should_retry_message(msg)
            # respect per-type cap
            allowed = max_retries_for(err_type) if max_retries is None else cap
            if not retryable or attempt >= allowed:
                raise
            # emit RETRY event
            try:
                err_payload = make_error_payload(err_type, component, msg, retryable=True,
                                                 trace_id=state.get("trace_id"))
                ev = make_event(state, "RETRY", component, status="retry",
                                metadata={"attempt": attempt + 1, "max_retries": allowed,
                                          "error_type": err_type, "message": msg[:300]},
                                error=err_payload)
                append_event(state, ev)
            except Exception:
                pass
            delay = base_delay_s * (2 ** attempt)
            logger.info(f"[retry] {component} attempt {attempt+1}/{allowed} after {delay}s: {err_type}: {msg[:120]}")
            time.sleep(delay)
    if last_exc:
        raise last_exc
    raise RuntimeError("retry exhausted without exception")
