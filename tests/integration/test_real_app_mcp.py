"""Integration tests for Real Application MCP Servers (GitHub, SQLite, Fetch)."""

import json
import pytest
from mcp_layer.client import MCPClient
from mcp_layer.models import MCPServerConfig
from mcp_layer.registry import registry
from mcp_layer.errors import MCPError


class TestRealAppDiscovery:
    """Test standard discovery and normalization across real application servers."""

    def test_github_server_discovery(self):
        cfg = MCPServerConfig(name="github", transport="stdio", command="python", args=["mcp_github_server.py"])
        client = MCPClient(cfg)
        tools = client.list_tools()
        names = [t["name"] for t in tools]
        assert "get_issue" in names
        assert "list_issues" in names
        assert "create_issue" in names
        assert "get_repository" in names

    def test_sqlite_server_discovery(self):
        cfg = MCPServerConfig(name="sqlite", transport="stdio", command="python", args=["mcp_sqlite_server.py"])
        client = MCPClient(cfg)
        tools = client.list_tools()
        names = [t["name"] for t in tools]
        assert "list_tables" in names
        assert "read_query" in names
        assert "create_record" in names
        assert "delete_record" in names

    def test_fetch_server_discovery(self):
        cfg = MCPServerConfig(name="fetch", transport="stdio", command="python", args=["mcp_fetch_server.py"])
        client = MCPClient(cfg)
        tools = client.list_tools()
        names = [t["name"] for t in tools]
        assert "get_url" in names
        assert "get_json" in names


class TestRealAppOperations:
    """Test read, write, and error operations on real applications."""

    def test_github_read_and_write(self):
        cfg = MCPServerConfig(name="github", transport="stdio", command="python", args=["mcp_github_server.py"])
        client = MCPClient(cfg)
        # Read
        res = client.call_tool("get_issue", {"issue_id": "issue_101"})
        data = json.loads(res)
        assert data.get("id") == "issue_101"
        assert "OAuth" in data.get("title", "")

        # Write
        w_res = client.call_tool("create_issue", {"repo": "personal_agent/assistant", "title": "Test Issue", "body": "Test Body"})
        w_data = json.loads(w_res)
        assert w_data.get("title") == "Test Issue"

    def test_sqlite_read_and_write(self):
        cfg = MCPServerConfig(name="sqlite", transport="stdio", command="python", args=["mcp_sqlite_server.py"])
        client = MCPClient(cfg)
        # Read
        res = client.call_tool("read_query", {"query": "SELECT * FROM users WHERE role='admin'"})
        rows = json.loads(res)
        assert len(rows) >= 1
        assert rows[0].get("name") == "Alice Smith"

        # Write
        w_res = client.call_tool("create_record", {"table_name": "users", "data": json.dumps({"name": "Test User", "email": "test@test.com", "role": "tester"})})
        w_data = json.loads(w_res)
        assert w_data.get("status") == "created"

    def test_sqlite_delete_confirmation_policy(self):
        registry._servers = {}
        registry.register_server(MCPServerConfig(name="sqlite", transport="stdio", command="python", args=["mcp_sqlite_server.py"]))
        registry.discover(force=True)
        assert registry.requires_confirmation("sqlite.delete_record", {"table_name": "users", "record_id": 1}) is True
        assert registry.requires_confirmation("sqlite.read_query", {"query": "SELECT 1"}) is False


class TestCrossAppWorkflow:
    """Test multi-app workflow without planner modifications."""

    def test_github_to_sqlite_data_flow(self):
        gh_client = MCPClient(MCPServerConfig(name="github", transport="stdio", command="python", args=["mcp_github_server.py"]))
        sql_client = MCPClient(MCPServerConfig(name="sqlite", transport="stdio", command="python", args=["mcp_sqlite_server.py"]))

        # Step 1: Read issue from GitHub
        iss = json.loads(gh_client.call_tool("get_issue", {"issue_id": "issue_102"}))
        assert iss.get("id") == "issue_102"

        # Step 2: Write audit log in SQLite
        log_res = json.loads(sql_client.call_tool("create_record", {
            "table_name": "audit_logs",
            "data": json.dumps({"action": "imported_issue", "timestamp": "2026-08-27", "details": iss.get("title")})
        }))
        assert log_res.get("status") == "created"

        # Step 3: Verify in SQLite
        verify = json.loads(sql_client.call_tool("read_query", {"query": f"SELECT * FROM audit_logs WHERE id={log_res.get('id')}"}))
        assert len(verify) == 1
        assert "SQLite" in verify[0].get("details", "")
