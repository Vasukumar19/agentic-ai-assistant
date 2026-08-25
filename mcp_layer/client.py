"""Generic MCP client — connect/disconnect/list_tools/call_tool with timeout and error mapping."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from .models import MCPServerConfig
from .errors import MCPError

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async coro from sync context (handles already-running loop)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # already in a loop — create new thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(asyncio.run, coro)
        return fut.result()


class MCPClient:
    """One client per server config. Handles stdio and streamable HTTP."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._connected = False

    # ---- public sync API (wraps async) ----

    def connect(self, timeout_s: float | None = None) -> None:
        return _run_async(self._connect_async(timeout_s or self.config.timeout_s))

    def disconnect(self) -> None:
        return _run_async(self._disconnect_async())

    def list_tools(self, timeout_s: float | None = None) -> list[dict[str, Any]]:
        return _run_async(self._list_tools_async(timeout_s or self.config.timeout_s))

    def call_tool(self, tool_name: str, arguments: dict[str, Any], timeout_s: float | None = None) -> str:
        return _run_async(self._call_tool_async(tool_name, arguments, timeout_s or self.config.timeout_s))

    # ---- async internals ----

    async def _connect_async(self, timeout_s: float) -> None:
        # probe connection by listing tools (lightweight)
        await self._list_tools_async(timeout_s)
        self._connected = True

    async def _disconnect_async(self) -> None:
        self._connected = False

    async def _list_tools_async(self, timeout_s: float) -> list[dict[str, Any]]:
        if not self.config.enabled:
            raise MCPError("MCP_CONNECTION_ERROR", f"server {self.config.name} is disabled", server=self.config.name)
        try:
            async with asyncio.timeout(timeout_s):
                if self.config.transport == "stdio":
                    return await self._list_tools_stdio()
                elif self.config.transport in ("http", "streamable_http"):
                    return await self._list_tools_http()
                else:
                    raise MCPError("MCP_PROTOCOL_ERROR", f"unknown transport {self.config.transport}", server=self.config.name)
        except TimeoutError as e:
            raise MCPError("MCP_TIMEOUT", f"list_tools timed out after {timeout_s}s", server=self.config.name) from e
        except MCPError:
            raise
        except Exception as e:
            raise MCPError("MCP_CONNECTION_ERROR", f"list_tools failed: {e}", server=self.config.name) from e

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any], timeout_s: float) -> str:
        if not self.config.enabled:
            raise MCPError("MCP_CONNECTION_ERROR", f"server {self.config.name} is disabled", server=self.config.name)
        try:
            async with asyncio.timeout(timeout_s):
                if self.config.transport == "stdio":
                    return await self._call_tool_stdio(tool_name, arguments)
                elif self.config.transport in ("http", "streamable_http"):
                    return await self._call_tool_http(tool_name, arguments)
                else:
                    raise MCPError("MCP_PROTOCOL_ERROR", f"unknown transport {self.config.transport}", server=self.config.name)
        except TimeoutError as e:
            raise MCPError("MCP_TIMEOUT", f"call_tool {tool_name} timed out after {timeout_s}s", server=self.config.name) from e
        except MCPError:
            raise
        except Exception as e:
            # unwrap cause for UnexpectedToolError etc.
            cause_msg = str(e.__cause__).lower() if getattr(e, "__cause__", None) else ""
            msg = (str(e).lower() + " " + cause_msg).strip()
            # also check McpError code if available
            err_code = getattr(e, "code", None) or getattr(getattr(e, "__cause__", None), "code", None)
            if err_code:
                msg += f" {str(err_code).lower()}"
            if "not found" in msg or "unknown tool" in msg or "tool not found" in msg:
                raise MCPError("MCP_TOOL_NOT_FOUND", f"tool {tool_name} not found: {e}", server=self.config.name) from e
            if "invalid" in msg or "validation" in msg or "argument" in msg:
                raise MCPError("MCP_INVALID_ARGUMENT", f"invalid args for {tool_name}: {e}", server=self.config.name) from e
            if "permission" in msg or "denied" in msg or "forbidden" in msg:
                raise MCPError("MCP_PERMISSION_ERROR", f"permission denied for {tool_name}: {e}", server=self.config.name) from e
            raise MCPError("MCP_SERVER_ERROR", f"call_tool {tool_name} failed: {e}", server=self.config.name) from e

    # ---- transport specifics ----

    async def _list_tools_stdio(self) -> list[dict[str, Any]]:
        from mcp.client.stdio import stdio_client
        from mcp import ClientSession, StdioServerParameters
        params = StdioServerParameters(
            command=self.config.command or "python",
            args=self.config.args or [],
            env=self.config.env or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
                out = []
                for t in resp.tools:
                    # SDK v2 uses input_schema, v1 uses inputSchema
                    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
                    # handle Pydantic model dumping if needed
                    if hasattr(schema, "model_dump"):
                        try:
                            schema = schema  # already dict-like
                        except Exception:
                            pass
                    out.append({
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": schema or {},
                    })
                return out

    async def _call_tool_stdio(self, tool_name: str, arguments: dict[str, Any]) -> str:
        from mcp.client.stdio import stdio_client
        from mcp import ClientSession, StdioServerParameters
        # MCP servers expect original tool name (without server prefix) — strip prefix if present
        raw_name = tool_name.split(".", 1)[-1] if "." in tool_name and tool_name.startswith(self.config.name + ".") else tool_name
        params = StdioServerParameters(
            command=self.config.command or "python",
            args=self.config.args or [],
            env=self.config.env or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(raw_name, arguments or {})
                parts = []
                for c in getattr(result, "content", []) or []:
                    if hasattr(c, "text"):
                        parts.append(c.text)
                    elif isinstance(c, dict) and "text" in c:
                        parts.append(c["text"])
                    else:
                        parts.append(str(c))
                joined = "".join(parts)
                # SDK v2 uses isError, v1 uses is_error — check both, plus content heuristic
                is_err = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
                if is_err or "Unknown tool" in joined or "Error:" in joined or "error:" in joined.lower():
                    low = joined.lower()
                    if "unknown tool" in low or "not found" in low:
                        raise MCPError("MCP_TOOL_NOT_FOUND", joined or "tool not found", server=self.config.name)
                    if "permission" in low or "denied" in low or "forbidden" in low:
                        raise MCPError("MCP_PERMISSION_ERROR", joined or "permission denied", server=self.config.name)
                    if "invalid" in low or "validation" in low or "argument" in low:
                        raise MCPError("MCP_INVALID_ARGUMENT", joined or "invalid argument", server=self.config.name)
                    raise MCPError("MCP_SERVER_ERROR", joined or "tool returned error", server=self.config.name)
                return joined if parts else json.dumps(getattr(result, "structuredContent", {}) or {}, ensure_ascii=False)

    async def _list_tools_http(self) -> list[dict[str, Any]]:
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        if not self.config.url:
            raise MCPError("MCP_CONNECTION_ERROR", "http transport requires url", server=self.config.name)
        async with streamable_http_client(self.config.url, headers=self.config.headers or None) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
                out = []
                for t in resp.tools:
                    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
                    out.append({"name": t.name, "description": t.description or "", "input_schema": schema or {}})
                return out

    async def _call_tool_http(self, tool_name: str, arguments: dict[str, Any]) -> str:
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        raw_name = tool_name.split(".", 1)[-1] if "." in tool_name and tool_name.startswith(self.config.name + ".") else tool_name
        if not self.config.url:
            raise MCPError("MCP_CONNECTION_ERROR", "http transport requires url", server=self.config.name)
        async with streamable_http_client(self.config.url, headers=self.config.headers or None) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(raw_name, arguments or {})
                parts = []
                for c in getattr(result, "content", []) or []:
                    if hasattr(c, "text"):
                        parts.append(c.text)
                    elif isinstance(c, dict) and "text" in c:
                        parts.append(c["text"])
                    else:
                        parts.append(str(c))
                joined = "".join(parts)
                is_err = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
                if is_err or "Unknown tool" in joined or "permission" in joined.lower() or "denied" in joined.lower():
                    low = joined.lower()
                    if "unknown tool" in low or "not found" in low:
                        raise MCPError("MCP_TOOL_NOT_FOUND", joined or "tool not found", server=self.config.name)
                    if "permission" in low or "denied" in low or "forbidden" in low:
                        raise MCPError("MCP_PERMISSION_ERROR", joined or "permission denied", server=self.config.name)
                    if "invalid" in low or "validation" in low or "argument" in low:
                        raise MCPError("MCP_INVALID_ARGUMENT", joined or "invalid argument", server=self.config.name)
                    raise MCPError("MCP_SERVER_ERROR", joined or "tool returned error", server=self.config.name)
                return joined if parts else json.dumps(getattr(result, "structuredContent", {}) or {}, ensure_ascii=False)
