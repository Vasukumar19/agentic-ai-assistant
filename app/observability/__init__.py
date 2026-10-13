"""Decoupled observability events and sinks."""

from app.observability.events import SystemTraceEvent, EventSeverity
from app.observability.sink import (
    IObservabilitySink,
    InMemorySink,
    JsonlFileSink,
    CompositeSink,
    default_sink,
    emit_event,
)

__all__ = [
    "SystemTraceEvent",
    "EventSeverity",
    "IObservabilitySink",
    "InMemorySink",
    "JsonlFileSink",
    "CompositeSink",
    "default_sink",
    "emit_event",
]
