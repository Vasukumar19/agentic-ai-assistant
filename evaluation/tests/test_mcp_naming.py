"""Part B — Tool naming evaluation: canonical vs alias."""

import pytest
from mcp_layer.registry import registry
from mcp_layer.models import NormalizedTool

def test_canonical_name_stable():
    # canonical is dot notation
    registry._discovered = False
    registry._servers = {}
    registry.load_servers_from_config([{"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"]}])
    registry.discover(force=True)
    norm = registry.get_normalized("test.lookup")
    assert norm is not None
    assert norm.name == "test.lookup"
    assert norm.original_name == "lookup"
    assert norm.server == "test"

def test_alias_resolves_to_canonical():
    registry._discovered = False
    registry._servers = {}
    registry.load_servers_from_config([{"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"]}])
    registry.discover(force=True)
    # alias test_lookup should exist and point to same server
    alias_norm = registry.get_normalized("test_lookup")
    assert alias_norm is not None
    assert alias_norm.server == "test"
    # both should be valid
    assert "test.lookup" in registry.valid_names()
    assert "test_lookup" in registry.valid_names()
    # both should resolve to a tool
    assert registry.get("test.lookup") is not None
    assert registry.get("test_lookup") is not None

def test_duplicate_alias_not_created_twice():
    registry._discovered = False
    registry._servers = {}
    registry.load_servers_from_config([{"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"]}])
    registry.discover(force=True)
    # second discover with force should not duplicate
    count_before = len(registry.valid_names())
    registry.discover(force=True)
    count_after = len(registry.valid_names())
    assert count_after == count_before

def test_collision_prevented():
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field
    class In(BaseModel):
        x: str = Field(description="x")
    dup = StructuredTool.from_function(func=lambda x: x, name="test.lookup", description="dup", args_schema=In)
    with pytest.raises(ValueError):
        registry.register_native(dup)

def test_unknown_alias_not_found():
    assert registry.get("nonexistent_tool_xyz") is None
    assert registry.get_normalized("nonexistent_tool_xyz") is None

def test_disabled_tool_not_discovered():
    registry._discovered = False
    registry._servers = {}
    registry.load_servers_from_config([{"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"], "enabled": False}])
    registry.discover(force=True)
    assert "test.lookup" not in registry.valid_names()
    # reset to enabled for other tests
    registry._discovered = False
    registry._servers = {}

def test_canonical_is_authoritative():
    # alias tool should call canonical via client, not have separate logic
    registry._discovered = False
    registry._servers = {}
    registry.load_servers_from_config([{"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"]}])
    registry.discover(force=True)
    # both should invoke same server tool and get same result
    res_dot = registry.get("test.echo").invoke({"message": "hi"})
    res_underscore = registry.get("test_echo").invoke({"message": "hi"})
    assert res_dot == res_underscore == "echo: hi"
