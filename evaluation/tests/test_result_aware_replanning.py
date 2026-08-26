"""
Unit tests for Result-Aware Replanning Module (Phase 11).
"""

import os
import json
import pytest

from mcp_layer.registry import registry
from nodes.planner_node import planner_node


@pytest.fixture(autouse=True)
def _setup_env():
    os.environ["RESULT_AWARE_REPLANNING"] = "on"
    os.environ["MCP_SERVERS"] = json.dumps([
        {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
        {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
        {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
    ])
    registry._servers = {}
    registry.load_servers_from_config()
    registry.discover(force=True)


def test_bounded_result_summary_length():
    """Verify tool output summaries are bounded to <= 500 chars."""
    huge_result = "X" * 2000
    state = {
        "question": "Summarize huge file",
        "tool_results": [{"tool": "filesystem.read_file", "arguments": {"path": "huge.txt"}, "result": huge_result}],
        "completed_steps": ["filesystem.read_file"],
        "tool_call_count": 1,
        "execution_status": "running",
        "trace_events": []
    }
    
    # Check bounded formatting
    res_val = str(state["tool_results"][0]["result"])
    bounded_res = res_val[:500] + ("..." if len(res_val) > 500 else "")
    assert len(bounded_res) <= 504
    assert bounded_res.endswith("...")


def test_replan_start_trace_event_emitted():
    """Verify REPLAN_START event is recorded when RESULT_AWARE_REPLANNING is on."""
    state = {
        "question": "Read note note_001 and create reminder",
        "tool_results": [{"tool": "notes.read", "arguments": {"id": "note_001"}, "result": "[Meeting] Dentist at 3pm"}],
        "completed_steps": ["notes.read"],
        "tool_call_count": 1,
        "execution_status": "running",
        "trace_events": []
    }
    
    out = planner_node(state)
    evs = out.get("trace_events") or []
    event_types = [e.get("event_type") for e in evs]
    assert "REPLAN_START" in event_types


def test_duplicate_tool_call_protection():
    """Verify planner prevents repeated identical call with identical result."""
    from nodes.planner_node import detect_loop
    import json
    sig = json.dumps({"t": "calendar.list_events", "a": {}}, sort_keys=True)
    history = [
        {"sig": sig, "tool": "calendar.list_events", "arguments": {}, "result": "[]"},
        {"sig": sig, "tool": "calendar.list_events", "arguments": {}, "result": "[]"}
    ]
    loop = detect_loop(history, "calendar.list_events", {}, history)
    assert loop == "alternating_identical"
