#!/usr/bin/env python
"""
Real local filesystem MCP server (Python) — exposes filesystem operations restricted to mcp_sandbox/.
Uses MCPServer (mcp 2.x) with stdio transport. This is a maintained local MCP server
providing real-world functionality, used because Node.js/npx is not available in this env.
"""

from pathlib import Path
from mcp.server.mcpserver import MCPServer

# sandbox root — only this directory is allowed
SANDBOX = Path(__file__).resolve().parent / "mcp_sandbox"
SANDBOX.mkdir(exist_ok=True)

mcp = MCPServer(name="filesystem", version="1.0.0")


@mcp.tool()
async def list_allowed_directories() -> str:
    """List allowed directories for filesystem operations."""
    return str(SANDBOX.resolve())


@mcp.tool()
async def list_directory(path: str = "") -> str:
    """List files and directories in the sandbox. Path is relative to sandbox root."""
    import os
    target = (SANDBOX / path).resolve()
    # security: must be within sandbox
    try:
        target.relative_to(SANDBOX.resolve())
    except ValueError:
        raise PermissionError(f"Access denied: {path} is outside sandbox")
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    items = []
    for p in sorted(target.iterdir()):
        items.append(f"{'DIR' if p.is_dir() else 'FILE'} {p.name}")
    return "\n".join(items) if items else "(empty)"


@mcp.tool()
async def read_file(path: str) -> str:
    """Read a file from the sandbox. Path is relative to sandbox root."""
    target = (SANDBOX / path).resolve()
    try:
        target.relative_to(SANDBOX.resolve())
    except ValueError:
        raise PermissionError(f"Access denied: {path} is outside sandbox")
    if not target.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"Not a file: {path}")
    # limit size to 10KB for sandbox
    data = target.read_text(encoding="utf-8", errors="replace")
    if len(data) > 10000:
        data = data[:10000] + "\n...[truncated]"
    return data


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write a file to the sandbox. Path is relative to sandbox root."""
    target = (SANDBOX / path).resolve()
    try:
        target.relative_to(SANDBOX.resolve())
    except ValueError:
        raise PermissionError(f"Access denied: {path} is outside sandbox")
    # ensure parent exists
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Successfully wrote to {path} ({len(content)} chars)"


@mcp.tool()
async def get_file_info(path: str) -> str:
    """Get file info (size, type) for a path in the sandbox."""
    import json
    target = (SANDBOX / path).resolve()
    try:
        target.relative_to(SANDBOX.resolve())
    except ValueError:
        raise PermissionError(f"Access denied: {path} is outside sandbox")
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    stat = target.stat()
    info = {"path": path, "is_file": target.is_file(), "is_dir": target.is_dir(), "size": stat.st_size}
    return json.dumps(info)


if __name__ == "__main__":
    import anyio
    anyio.run(mcp.run_stdio_async)
