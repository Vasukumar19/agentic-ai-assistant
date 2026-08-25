"""Standardised error taxonomy and helpers."""

from __future__ import annotations

from enum import Enum


class ErrorType(str, Enum):
    MODEL_ERROR = "MODEL_ERROR"
    PLANNER_ERROR = "PLANNER_ERROR"
    ROUTING_ERROR = "ROUTING_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TOOL_SELECTION_ERROR = "TOOL_SELECTION_ERROR"
    TOOL_ARGUMENT_ERROR = "TOOL_ARGUMENT_ERROR"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    MEMORY_ERROR = "MEMORY_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


# which error types are retryable by default
RETRYABLE = {
    ErrorType.NETWORK_ERROR,
    ErrorType.TIMEOUT_ERROR,
    ErrorType.RATE_LIMIT_ERROR,
    ErrorType.INFRASTRUCTURE_ERROR,
}

# per-error retry caps (conservative)
RETRY_CAPS = {
    ErrorType.NETWORK_ERROR: 2,
    ErrorType.TIMEOUT_ERROR: 1,
    ErrorType.RATE_LIMIT_ERROR: 1,
    ErrorType.INFRASTRUCTURE_ERROR: 1,
}

DEFAULT_MAX_RETRIES = 1


def is_retryable(error_type: str) -> bool:
    try:
        return ErrorType(error_type) in RETRYABLE
    except ValueError:
        return False


def max_retries_for(error_type: str) -> int:
    try:
        return RETRY_CAPS.get(ErrorType(error_type), DEFAULT_MAX_RETRIES if is_retryable(error_type) else 0)
    except ValueError:
        return 0


def classify_error(exc: Exception, component: str = "unknown") -> str:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    # network
    if any(k in msg for k in ["connecterror", "connection", "dns", "no records found", "name resolution", "client error (connect)"]):
        return ErrorType.NETWORK_ERROR.value
    if "timeout" in msg or "timed out" in msg or isinstance(exc, TimeoutError):
        return ErrorType.TIMEOUT_ERROR.value
    if "rate limit" in msg or "429" in msg or "too many requests" in msg:
        return ErrorType.RATE_LIMIT_ERROR.value
    if "ddgsexception" in name or "ddgs" in msg:
        # ddgs wraps network errors; already caught above, else tool execution
        return ErrorType.TOOL_EXECUTION_ERROR.value
    if component in ("planner", "planner_node"):
        return ErrorType.PLANNER_ERROR.value
    if component in ("router", "intent_router"):
        return ErrorType.ROUTING_ERROR.value
    if component in ("rag_retriever", "retrieval", "bm25", "faiss", "reranker"):
        return ErrorType.RETRIEVAL_ERROR.value
    if component in ("memory", "memory_retriever", "memory_extractor", "memory_saver"):
        return ErrorType.MEMORY_ERROR.value
    if "validation" in msg or "pydantic" in msg:
        return ErrorType.VALIDATION_ERROR.value
    return ErrorType.UNKNOWN_ERROR.value


def make_error_payload(error_type: str, component: str, message: str, retryable: bool | None = None, trace_id: str | None = None) -> dict:
    if retryable is None:
        retryable = is_retryable(error_type)
    return {
        "error_type": error_type,
        "component": component,
        "message": message[:500],
        "retryable": retryable,
        "trace_id": trace_id,
    }
