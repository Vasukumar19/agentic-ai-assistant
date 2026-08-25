"""MCP error taxonomy — maps to existing observability ErrorType."""

from __future__ import annotations

from observability.errors import ErrorType


MCP_ERROR_MAP = {
    "MCP_CONNECTION_ERROR": ErrorType.NETWORK_ERROR.value,
    "MCP_TOOL_NOT_FOUND": ErrorType.TOOL_SELECTION_ERROR.value,
    "MCP_INVALID_ARGUMENT": ErrorType.TOOL_ARGUMENT_ERROR.value,
    "MCP_PERMISSION_ERROR": ErrorType.TOOL_EXECUTION_ERROR.value,
    "MCP_TIMEOUT": ErrorType.TIMEOUT_ERROR.value,
    "MCP_SERVER_ERROR": ErrorType.TOOL_EXECUTION_ERROR.value,
    "MCP_PROTOCOL_ERROR": ErrorType.TOOL_EXECUTION_ERROR.value,
}

# which MCP errors are retryable
MCP_RETRYABLE = {
    "MCP_CONNECTION_ERROR",
    "MCP_TIMEOUT",
    "MCP_SERVER_ERROR",
}


def mcp_error_type_to_observability(mcp_error: str) -> str:
    return MCP_ERROR_MAP.get(mcp_error, ErrorType.UNKNOWN_ERROR.value)


def is_mcp_retryable(mcp_error: str) -> bool:
    return mcp_error in MCP_RETRYABLE


class MCPError(Exception):
    """Base MCP error with typed code."""
    def __init__(self, code: str, message: str, server: str | None = None, retryable: bool | None = None):
        super().__init__(message)
        self.code = code
        self.server = server
        self.retryable = retryable if retryable is not None else is_mcp_retryable(code)

    def to_observability_type(self) -> str:
        return mcp_error_type_to_observability(self.code)
