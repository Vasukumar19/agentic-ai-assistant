#!/usr/bin/env python
"""
Deterministic MCP test server — exposes test.echo, test.add, test.lookup, test.write
Run via: python mcp_test_server.py  (stdio transport)
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="test", version="1.0.0")

# in-memory storage for test.write
_store: dict[str, str] = {}

@mcp.tool()
async def echo(message: str) -> str:
    """Echo back the message."""
    return f"echo: {message}"

@mcp.tool()
async def add(a: int, b: int) -> str:
    """Add two integers."""
    return str(a + b)

@mcp.tool()
async def lookup(query: str) -> str:
    """Deterministic lookup — returns fixed structure for any query."""
    import json
    data = {"value": 42, "query": query, "items": ["alpha", "beta"], "count": 7}
    return json.dumps(data)

@mcp.tool()
async def write(key: str, value: str) -> str:
    """Store a value in temporary test storage."""
    _store[key] = value
    return f"stored {key}={value} (total {len(_store)} keys)"

@mcp.tool()
async def fail(mode: str = "error") -> str:
    """Simulate failure modes for testing."""
    if mode == "error":
        raise ValueError("simulated tool error: invalid argument")
    if mode == "timeout":
        import asyncio
        await asyncio.sleep(10)
        return "should have timed out"
    if mode == "permission":
        raise PermissionError("simulated permission denied")
    return f"fail mode {mode} ok"

if __name__ == "__main__":
    # run via stdio (client will launch this as subprocess)
    import anyio
    anyio.run(mcp.run_stdio_async)
