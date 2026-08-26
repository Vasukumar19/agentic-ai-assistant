"""
Unit tests for Generic MCP Capability Discovery & Tool Filtering (Phase 10).
"""

import os
import json
import pytest

from mcp_layer.registry import registry
from nodes.tools import web_search_tool, calculator
from mcp_layer.discovery import discover_tools, CapabilityDiscoverer, score_text_similarity


@pytest.fixture(autouse=True)
def _setup_registry():
    """Ensure registry has native + MCP tools registered for testing."""
    os.environ["MCP_SERVERS"] = json.dumps([
        {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
        {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
        {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
    ])
    if "web_search" not in registry._native:
        registry.register_native(web_search_tool)
    if "calculator" not in registry._native:
        registry.register_native(calculator)
    registry._servers = {}
    registry.load_servers_from_config()
    registry.discover(force=True)


def test_score_text_similarity_basic():
    query_tokens = {"meeting", "calendar"}
    doc = "list events in my calendar schedule meetings"
    score = score_text_similarity(query_tokens, doc, doc_name="calendar.list_events")
    assert score > 0.3


def test_metadata_discovery_calendar_query():
    disc = CapabilityDiscoverer(registry=registry)
    servers, tools, conf, fallback = disc.discover_metadata("List all my calendar events on 2026-09-01.")
    assert "calendar" in servers
    assert any("calendar" in t for t in tools)
    assert not fallback


def test_metadata_discovery_notes_query():
    disc = CapabilityDiscoverer(registry=registry)
    servers, tools, conf, fallback = disc.discover_metadata("Read note note_001 and tell me what it says.")
    assert "notes" in servers
    assert any("notes" in t for t in tools)
    assert not fallback


def test_metadata_discovery_calculator_query():
    disc = CapabilityDiscoverer(registry=registry)
    servers, tools, conf, fallback = disc.discover_metadata("Calculate 128 / 8")
    assert "calculator" in tools


def test_metadata_discovery_fallback_on_empty_query():
    disc = CapabilityDiscoverer(registry=registry)
    servers, tools, conf, fallback = disc.discover_metadata("xyz123abc456_random_gibberish")
    assert fallback is True
    assert len(tools) == len(registry.valid_names())


def test_discover_tools_trace_events():
    state = {"trace_events": []}
    servers, tools, conf, fallback, dur = discover_tools(
        state, "Create a reminder for dentist tomorrow", strategy="metadata"
    )
    assert len(state["trace_events"]) >= 2
    event_types = [e["event_type"] for e in state["trace_events"]]
    assert "DISCOVERY_START" in event_types
    assert "DISCOVERY_RESULT" in event_types
    result_ev = [e for e in state["trace_events"] if e["event_type"] == "DISCOVERY_RESULT"][0]
    assert "selected_tools" in result_ev["metadata"]
    assert "confidence" in result_ev["metadata"]


def test_native_tool_preservation():
    disc = CapabilityDiscoverer(registry=registry)
    servers, tools, conf, fallback = disc.discover_metadata("Calculate 25 * 40 and search web for news.")
    assert "calculator" in tools
    assert "web_search" in tools
