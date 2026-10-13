"""Tool manifest, capability classifications, and typed result envelopes."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SideEffectLevel(str, Enum):
    """Classification of tool mutation impact."""
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    IRREVERSIBLE_WRITE = "IRREVERSIBLE_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class ApprovalRequirement(str, Enum):
    """Deterministic human-in-the-loop requirement policy."""
    NEVER = "NEVER"
    ALWAYS = "ALWAYS"
    CONDITIONAL = "CONDITIONAL"


class ToolErrorCode(str, Enum):
    """Categorized tool execution error codes."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolManifest(BaseModel):
    """Explicit capability declaration for all tools."""
    name: str  # Fully qualified: "notes.delete"
    version: str = "1.0.0"
    description: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    side_effect: SideEffectLevel = SideEffectLevel.READ_ONLY
    approval: ApprovalRequirement = ApprovalRequirement.NEVER
    idempotent: bool = True
    timeout_seconds: float = 30.0


class ToolResultEnvelope(BaseModel):
    """Standardized result returned by the Tool Gateway for every execution."""
    status: str  # "success" | "error" | "awaiting_approval"
    tool_name: str
    data: Optional[Dict[str, Any]] = None
    error_code: Optional[ToolErrorCode] = None
    error_message: Optional[str] = None
    retryable: bool = False
    duration_ms: int = 0

    @classmethod
    def success(cls, tool_name: str, data: Dict[str, Any], duration_ms: int = 0) -> ToolResultEnvelope:
        return cls(
            status="success",
            tool_name=tool_name,
            data=data,
            duration_ms=duration_ms,
        )

    @classmethod
    def error(
        cls,
        tool_name: str,
        error_code: ToolErrorCode,
        error_message: str,
        retryable: bool = False,
        duration_ms: int = 0,
    ) -> ToolResultEnvelope:
        return cls(
            status="error",
            tool_name=tool_name,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            duration_ms=duration_ms,
        )

    @classmethod
    def awaiting_approval(
        cls,
        tool_name: str,
        approval_token: str,
        summary: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ToolResultEnvelope:
        payload = {"approval_token": approval_token, "summary": summary}
        if data:
            payload.update(data)
        return cls(
            status="awaiting_approval",
            tool_name=tool_name,
            data=payload,
        )
