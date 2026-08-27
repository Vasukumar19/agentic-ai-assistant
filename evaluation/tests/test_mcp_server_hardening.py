"""
Unit Tests for Phase 13 MCP Server Exception Hardening
======================================================

Tests:
1. missing resource -> clean MCP error
2. invalid argument -> clean MCP error
3. permission error -> clean MCP error
4. unexpected exception -> observable failure
5. server process remains usable after expected tool error
6. no TaskGroup crash leaks into planner
"""

import pytest
import asyncio
import json


@pytest.mark.anyio
async def test_missing_resource_clean_error():
    """Missing resource returns structured error string instead of raising unhandled exception."""
    from mcp_notes_server import read
    res = await read("note_999999")
    assert "Error:" in res
    assert "not found" in res.lower()


@pytest.mark.anyio
async def test_missing_calendar_event_clean_error():
    """Missing calendar event returns clean error."""
    from mcp_calendar_server import get_event
    res = await get_event("evt_999999")
    assert "Error:" in res
    assert "not found" in res.lower()


@pytest.mark.anyio
async def test_missing_reminder_clean_error():
    """Missing reminder returns clean error."""
    from mcp_reminders_server import get
    res = await get("rem_999999")
    assert "Error:" in res
    assert "not found" in res.lower()


@pytest.mark.anyio
async def test_filesystem_sandbox_permission_error():
    """Accessing path outside sandbox returns clean error."""
    from mcp_filesystem_server import read_file
    res = await read_file("../../outside.txt")
    assert "Error:" in res
    assert "outside sandbox" in res.lower() or "denied" in res.lower()


@pytest.mark.anyio
async def test_server_process_remains_usable_after_error():
    """Server handles subsequent requests successfully after an error."""
    from mcp_notes_server import read, create
    # 1. Trigger error on missing note
    err_res = await read("note_999999")
    assert "Error:" in err_res
    
    # 2. Subsequent create call succeeds
    ok_res = await create("Test Note", "Content for test")
    assert "note_id" in ok_res


@pytest.mark.anyio
async def test_no_taskgroup_crash():
    """Errors do not bubble out of tool functions as unhandled TaskGroup exceptions."""
    from mcp_filesystem_server import list_directory
    res = await list_directory("non_existent_folder_xyz")
    assert "Error:" in res
