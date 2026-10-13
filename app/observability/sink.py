"""Decoupled Observability Sink implementations."""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.context import ExecutionContext
from app.observability.events import SystemTraceEvent, EventSeverity

logger = logging.getLogger(__name__)


class IObservabilitySink(ABC):
    """Abstract interface for observability sinks."""

    @abstractmethod
    def emit(self, event: SystemTraceEvent) -> None:
        """Emit a trace event synchronously."""
        pass


class InMemorySink(IObservabilitySink):
    """Thread-safe in-memory sink for testing and verification."""

    def __init__(self):
        self._events: List[SystemTraceEvent] = []
        self._lock = threading.Lock()

    def emit(self, event: SystemTraceEvent) -> None:
        with self._lock:
            self._events.append(event)

    def get_events(self) -> List[SystemTraceEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class JsonlFileSink(IObservabilitySink):
    """Thread-safe persistent JSONL file sink."""

    def __init__(self, trace_dir: Optional[Path] = None):
        self.trace_dir = trace_dir or settings.TRACES_DIR
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, event: SystemTraceEvent) -> None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        file_path = self.trace_dir / f"trace_{date_str}.jsonl"
        line = json.dumps(event.to_dict()) + "\n"
        with self._lock:
            try:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                logger.error("Failed to write trace event to %s: %s", file_path, e)


class CompositeSink(IObservabilitySink):
    """Fan-out to multiple sinks."""

    def __init__(self, sinks: List[IObservabilitySink]):
        self.sinks = sinks

    def emit(self, event: SystemTraceEvent) -> None:
        for s in self.sinks:
            try:
                s.emit(event)
            except Exception as e:
                logger.error("Error in sink %s: %s", type(s).__name__, e)


# Global default sink
_default_file_sink = JsonlFileSink()
_default_memory_sink = InMemorySink()
default_sink: IObservabilitySink = CompositeSink([_default_file_sink, _default_memory_sink])


def emit_event(
    ctx: ExecutionContext,
    component: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
    severity: EventSeverity = EventSeverity.INFO,
    error_details: Optional[Dict[str, Any]] = None,
    sink: Optional[IObservabilitySink] = None,
) -> SystemTraceEvent:
    """Helper to construct and emit a strongly-typed trace event from ExecutionContext."""
    active_sink = sink or default_sink
    event = SystemTraceEvent(
        correlation_id=ctx.correlation_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        execution_id=ctx.execution_id,
        step_id=ctx.step_id,
        component=component,
        event_type=event_type,
        severity=severity,
        duration_ms=duration_ms,
        payload=payload or {},
        error_details=error_details,
    )
    active_sink.emit(event)
    return event
