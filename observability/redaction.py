"""Safe serialization / redaction layer for tool outputs."""

from __future__ import annotations

import json
from typing import Any

# hard caps to avoid dumping huge pages into traces
MAX_STR_LEN = 400
MAX_LIST_ITEMS = 5
SENSITIVE_KEYS = {"api_key", "password", "secret", "token", "credential", "authorization"}


def redact_value(key: str, value: Any) -> Any:
    if key.lower() in SENSITIVE_KEYS:
        return "***REDACTED***"
    return value


def _truncate_str(s: str) -> str:
    if len(s) > MAX_STR_LEN:
        return s[:MAX_STR_LEN] + f"...[truncated {len(s)-MAX_STR_LEN} chars]"
    return s


def safe_serialize(value: Any, max_len: int = MAX_STR_LEN) -> Any:
    """Return a JSON-serializable, truncated, redacted view of value."""
    try:
        if value is None:
            return None
        if isinstance(value, str):
            return _truncate_str(value)
        if isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, dict):
            out = {}
            for k, v in list(value.items())[:MAX_LIST_ITEMS * 2]:
                out[str(k)] = redact_value(str(k), safe_serialize(v, max_len))
            if len(value) > MAX_LIST_ITEMS * 2:
                out["..."] = f"+{len(value) - MAX_LIST_ITEMS*2} more keys"
            return out
        if isinstance(value, (list, tuple)):
            items = [safe_serialize(x, max_len) for x in list(value)[:MAX_LIST_ITEMS]]
            if len(value) > MAX_LIST_ITEMS:
                items.append(f"... +{len(value)-MAX_LIST_ITEMS} more")
            return items
        # fallback: stringify safely
        return _truncate_str(str(value))
    except Exception:
        return "[unserializable]"


def summarize_tool_result(tool_name: str, result: str) -> dict:
    """Produce compact metadata for a tool result (no raw dump)."""
    s = str(result or "")
    return {
        "tool": tool_name,
        "result_chars": len(s),
        "result_preview": _truncate_str(s),
        "is_error": s.lower().startswith("error"),
    }
