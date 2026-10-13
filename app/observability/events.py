"""Strongly-typed Observability Event Schemas for V2."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class SystemTraceEvent(BaseModel):
    """
    Immutable structured trace event emitted to decoupled telemetry sinks.
    Does NOT mutate or attach to conversational graph state.
    """
    event_id: str = Field(default_factory=lambda: f"ev_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}")
    correlation_id: str
    user_id: str
    session_id: str
    execution_id: str
    step_id: Optional[str] = None
    component: str  # "router", "knowledge", "planner", "gateway", etc.
    event_type: str  # "REQUEST", "RETRIEVAL", "TOOL_CALL", "FINAL_ANSWER", "ERROR", etc.
    severity: EventSeverity = EventSeverity.INFO
    duration_ms: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    error_details: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable dictionary."""
        return self.model_dump()
