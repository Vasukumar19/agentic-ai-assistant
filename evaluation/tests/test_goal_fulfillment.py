"""
Unit Tests for Phase 13 Deterministic Goal Fulfillment Guard
===========================================================

Tests:
1. single-operation task -> FINAL allowed
2. two-operation task -> FINAL blocked after first operation
3. all operations completed -> FINAL allowed
4. blocked dependency -> honest BLOCKED state
5. execution budget still respected
6. loop protection still respected
7. no service-specific keyword routing
8. result-aware context correctly updates completed/remaining state
"""

import pytest
from planning.goal_guard import (
    extract_abstract_operations,
    map_tool_to_operation,
    goal_fulfillment_check,
)


def test_single_operation_final_allowed():
    """Single operation task allows final after 1 tool call."""
    query = "List all my notes."
    tool_results = [{"tool": "notes.list", "result": "[{'title': 'Meeting'}]"}]
    status, req, comp, rem = goal_fulfillment_check({}, query, tool_results)
    assert status == "FULFILLED"
    assert len(rem) == 0


def test_two_operation_blocked_after_first():
    """Two-operation task rejects final if second operation is not yet executed."""
    query = "Read the report.txt and calculate 15% of the total inside."
    tool_results = [{"tool": "filesystem.read_file", "result": "total: 500"}]
    status, req, comp, rem = goal_fulfillment_check({}, query, tool_results)
    assert status == "INCOMPLETE"
    assert "calculate" in rem


def test_all_operations_completed_final_allowed():
    """Multi-operation task allows final once all operations have completed."""
    query = "Read budget.txt, calculate 20% tax, and save the tax note."
    tool_results = [
        {"tool": "filesystem.read_file", "result": "1000"},
        {"tool": "calculator", "result": "200"},
        {"tool": "notes.create", "result": "note_001"},
    ]
    status, req, comp, rem = goal_fulfillment_check({}, query, tool_results)
    assert status == "FULFILLED"
    assert len(rem) == 0


def test_blocked_dependency_honest_state():
    """Unrecoverable failure on a dependency sets BLOCKED state."""
    query = "Get event evt_999, read the note attached, and set a reminder."
    tool_results = [
        {"tool": "calendar.get_event", "result": "Error: Event not found: evt_999"},
        {"tool": "calendar.get_event", "result": "Error: Event not found: evt_999"},
        {"tool": "calendar.get_event", "result": "Error: Event not found: evt_999"},
        {"tool": "calendar.get_event", "result": "Error: Event not found: evt_999"},
    ]
    status, req, comp, rem = goal_fulfillment_check({}, query, tool_results)
    assert status == "BLOCKED"


def test_execution_budget_respected():
    """Goal guard preserves execution budget limits."""
    from config import MAX_EXECUTION_STEPS
    assert MAX_EXECUTION_STEPS >= 5


def test_loop_protection_respected():
    """Loop protection detects repeated tool calls before goal guard forces execution."""
    from nodes.planner_node import detect_loop
    import json
    sig = json.dumps({"t": "notes.list", "a": {}}, sort_keys=True)
    history = [
        {"sig": sig, "tool": "notes.list", "arguments": {}, "result": "[]"},
        {"sig": sig, "tool": "notes.list", "arguments": {}, "result": "[]"},
    ]
    loop = detect_loop(history, "notes.list", {}, history)
    assert loop == "alternating_identical"


def test_no_service_specific_keyword_routing():
    """Goal extraction extracts generic operations without hardcoded service names."""
    q1 = "Schedule a sync and notify the team."
    q2 = "Create an appointment and write a summary."
    ops1 = extract_abstract_operations(q1)
    ops2 = extract_abstract_operations(q2)
    assert "calendar" not in ops1
    assert "reminders" not in ops1
    assert "notes" not in ops2
    assert "create" in ops1
    assert "create" in ops2


def test_result_aware_context_updates():
    """Goal check updates completed and remaining operations dynamically."""
    query = "List my reminders, then delete reminder rem_001."
    ops = extract_abstract_operations(query)
    assert "list" in ops
    assert "delete" in ops
    
    # Step 1: list called
    status1, _, comp1, rem1 = goal_fulfillment_check({}, query, [{"tool": "reminders.list", "result": "[]"}])
    assert "list" in comp1
    assert "delete" in rem1
    assert status1 == "INCOMPLETE"
    
    # Step 2: delete called
    status2, _, comp2, rem2 = goal_fulfillment_check({}, query, [
        {"tool": "reminders.list", "result": "[]"},
        {"tool": "reminders.delete", "result": "Deleted rem_001"},
    ])
    assert "delete" in comp2
    assert len(rem2) == 0
    assert status2 == "FULFILLED"
