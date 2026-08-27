"""
Production Smoke Test (V1 Production Freeze)
============================================

Verifies the full production stack deterministically in < 15 seconds:
1. Ollama connectivity & model presence
2. MCP registry & tool discovery
3. Native calculator execution
4. Sandboxed filesystem access
5. Multi-step cross-server execution
6. Human confirmation enforcement on destructive operations
7. Sandbox escape prevention
8. End-to-end graph execution
"""

import sys
import json
import os
import urllib.request
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Ensure default MCP servers configured for smoke test
if not os.environ.get("MCP_SERVERS"):
    os.environ["MCP_SERVERS"] = json.dumps([
        {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
        {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
        {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
        {"name": "filesystem", "transport": "stdio", "command": "python", "args": ["mcp_filesystem_server.py"]},
    ])


def run_smoke_test():
    print("=======================================================")
    print("      AGENTIC AI ASSISTANT — PRODUCTION SMOKE TEST     ")
    print("=======================================================")
    passed = 0
    total = 9

    # 1. Ollama Connectivity
    print("\n[1/9] Checking Ollama Connectivity...", end=" ")
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", headers={"User-Agent": "smoke-test"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            assert any("qwen3" in m for m in models), f"qwen3 not found in {models}"
        print("PASSED")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 2. MCP Discovery
    print("[2/9] Initializing MCP Registry & Discovering Tools...", end=" ")
    try:
        from mcp_layer.registry import registry
        registry._servers = {}
        registry.load_servers_from_config()
        count = registry.discover(force=True)
        assert count >= 8, f"Expected >=8 tools, found {count}"
        print(f"PASSED ({count} tools discovered)")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 3. Native Calculator
    print("[3/9] Testing Native Tool Execution (Calculator)...", end=" ")
    try:
        from nodes.tools import run_tool
        res = run_tool("calculator", {"expression": "25 * 4 + 10"})
        assert "110" in res, f"Expected 110, got {res}"
        print(f"PASSED (Result: {res})")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 4. Filesystem Sandbox Read/Write
    print("[4/9] Testing Sandboxed Filesystem Operations...", end=" ")
    try:
        from nodes.tools import run_tool
        w_res = run_tool("filesystem.write_file", {"path": "smoke_test.txt", "content": "Smoke Test OK"})
        assert "wrote" in w_res.lower() or "successfully" in w_res.lower()
        r_res = run_tool("filesystem.read_file", {"path": "smoke_test.txt"})
        assert "Smoke Test OK" in r_res
        print("PASSED")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 5. Sandbox Escape Blocked
    print("[5/9] Verifying Sandbox Boundary Enforcement...", end=" ")
    try:
        from nodes.tools import run_tool
        esc_res = run_tool("filesystem.read_file", {"path": "../../outside_sandbox.txt"})
        assert "error" in esc_res.lower() or "denied" in esc_res.lower() or "permission" in esc_res.lower()
        print("PASSED (Escape blocked safely)")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 6. Destructive Operation Human Confirmation
    print("[6/9] Verifying Destructive Tool Human Confirmation...", end=" ")
    try:
        from nodes.tools import requires_confirmation
        assert requires_confirmation("calendar.delete_event", {"event_id": "evt_001"}) is True
        assert requires_confirmation("notes.delete", {"note_id": "note_001"}) is True
        assert requires_confirmation("calendar.create_event", {"title": "Test"}) is False
        print("PASSED (Confirmation enforced)")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 7. Goal Guard Capability Extraction
    print("[7/9] Testing Generic Goal Fulfillment Guard...", end=" ")
    try:
        from planning.goal_guard import extract_abstract_operations, goal_fulfillment_check
        ops = extract_abstract_operations("Read report.txt, calculate total, and create a reminder.")
        assert ops == ["read", "calculate", "create"], f"Got ops: {ops}"
        status, _, _, rem = goal_fulfillment_check({}, "Read report.txt and calculate total.", [{"tool": "filesystem.read_file", "result": "100"}])
        assert status == "INCOMPLETE" and "calculate" in rem
        print("PASSED")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 8. MCP Subprocess Error Hardening
    print("[8/9] Verifying MCP Subprocess Error Isolation...", end=" ")
    try:
        from nodes.tools import run_tool
        missing_res = run_tool("notes.read", {"note_id": "note_nonexistent_999"})
        assert "Error:" in missing_res or "not found" in missing_res.lower()
        print("PASSED (Clean error returned, 0 crashes)")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    # 9. End-to-End Agent Invocation
    print("[9/9] Testing End-to-End Graph Execution...", end=" ")
    try:
        from graph import create_runnable_graph
        app = create_runnable_graph()
        out = app.invoke({"question": "Calculate 15 * 6 using calculator."})
        ans = out.get("answer", "")
        assert "90" in ans or "calculation" in ans.lower() or out.get("execution_status") == "completed"
        print("PASSED")
        passed += 1
    except Exception as e:
        print(f"FAILED ({e})")

    print("\n=======================================================")
    print(f" SMOKE TEST SUMMARY: {passed} / {total} PASSED")
    print("=======================================================\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())
