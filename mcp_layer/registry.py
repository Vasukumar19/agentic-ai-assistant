"""ToolRegistry — single source of truth for native + MCP tools."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from langchain_core.tools import StructuredTool

from .models import NormalizedTool, MCPServerConfig
from .errors import MCPError
from .client import MCPClient
from .adapter import mcp_tool_to_langchain

logger = logging.getLogger(__name__)

# default policy inference based on tool name substrings
def _infer_policy(tool_name: str, server: str, explicit: dict | None = None) -> dict[str, Any]:
    if explicit and tool_name in explicit:
        return explicit[tool_name]
    # also check raw name
    raw = tool_name.split(".")[-1]
    if explicit and raw in explicit:
        return explicit[raw]
    low = tool_name.lower()
    if any(x in low for x in ["delete", "remove", "destroy", "drop"]):
        return {"operation": "destructive", "risk_level": "high", "requires_confirmation": True}
    if any(x in low for x in ["create", "write", "update", "send", "insert", "add"]):
        return {"operation": "write", "risk_level": "medium", "requires_confirmation": False}
    return {"operation": "read", "risk_level": "low", "requires_confirmation": False}


class ToolRegistry:
    """Holds native + MCP tools, guarantees unique names, validates."""

    def __init__(self):
        self._native: dict[str, Any] = {}  # name -> StructuredTool
        self._mcp: dict[str, Any] = {}  # prefixed name -> StructuredTool
        self._normalized: dict[str, NormalizedTool] = {}  # name -> NormalizedTool
        self._clients: dict[str, MCPClient] = {}  # server name -> client
        self._servers: dict[str, MCPServerConfig] = {}
        self._discovered = False

    # ---- native registration ----

    def register_native(self, tool) -> None:
        name = tool.name
        if name in self._native or name in self._mcp:
            raise ValueError(f"tool name collision: {name} already registered")
        self._native[name] = tool
        self._normalized[name] = NormalizedTool(
            name=name, description=tool.description or "", input_schema=getattr(tool.args_schema, "model_json_schema", lambda: {})() if getattr(tool, "args_schema", None) else {},
            source="native", server=None, operation="read", risk_level="low", requires_confirmation=False, enabled=True, original_name=name)

    def register_native_many(self, tools: list) -> None:
        for t in tools:
            self.register_native(t)

    # ---- MCP discovery ----

    def load_servers_from_config(self, servers: list[dict[str, Any]] | None = None) -> None:
        """Load server configs from explicit list or env MCP_SERVERS (json)."""
        if servers is None:
            raw = os.getenv("MCP_SERVERS", "").strip()
            if not raw:
                # also support file path
                cfg_path = os.getenv("MCP_CONFIG_FILE", "")
                if cfg_path and os.path.exists(cfg_path):
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            servers = data.get("mcpServers") or data.get("servers") or []
                    except Exception as e:
                        logger.warning(f"failed to load MCP config file {cfg_path}: {e}")
                        servers = []
                else:
                    servers = []
            else:
                try:
                    # try json array
                    servers = json.loads(raw)
                except json.JSONDecodeError:
                    # try single server json object
                    try:
                        obj = json.loads(raw)
                        servers = [obj] if isinstance(obj, dict) else []
                    except Exception:
                        servers = []
        for s in servers or []:
            try:
                cfg = MCPServerConfig(**s)
                self._servers[cfg.name] = cfg
            except Exception as e:
                logger.warning(f"invalid MCP server config {s}: {e}")

    def discover(self, force: bool = False) -> int:
        """Connect to each enabled server, list tools, register them. Returns count of new tools."""
        if self._discovered and not force:
            return 0
        if force:
            # clear existing MCP tools so policy updates can be re-applied
            for k in list(self._mcp.keys()):
                # remove tools that belong to servers being rediscovered
                # for simplicity, clear all MCP (native stays)
                del self._mcp[k]
            for k in list(self._normalized.keys()):
                if self._normalized[k].source == "mcp":
                    del self._normalized[k]
        if not self._servers:
            self.load_servers_from_config()
        count = 0
        for name, cfg in list(self._servers.items()):
            if not cfg.enabled:
                continue
            client = MCPClient(cfg)
            self._clients[name] = client
            try:
                tools = client.list_tools(timeout_s=cfg.timeout_s)
                for spec in tools:
                    raw_name = spec.get("name") or "unknown"
                    prefixed = f"{name}.{raw_name}" if not raw_name.startswith(name + ".") else raw_name
                    if prefixed in self._native:
                        logger.warning(f"tool collision skipped (native): {prefixed}")
                        continue
                    if prefixed in self._mcp and not force:
                        logger.warning(f"tool collision skipped: {prefixed}")
                        continue
                    # if force and already exists, remove old entry to allow policy update
                    if prefixed in self._mcp and force:
                        del self._mcp[prefixed]
                        if prefixed in self._normalized:
                            del self._normalized[prefixed]
                    policy = _infer_policy(prefixed, name, cfg.tool_policy)
                    norm = NormalizedTool(
                        name=prefixed, description=spec.get("description", ""),
                        input_schema=spec.get("input_schema") or {},
                        source="mcp", server=name,
                        operation=policy.get("operation", "read"),
                        risk_level=policy.get("risk_level", "low"),
                        requires_confirmation=bool(policy.get("requires_confirmation", False)),
                        timeout_s=cfg.timeout_s, enabled=True, original_name=raw_name)
                    # adapter to LangChain
                    lc_tool = mcp_tool_to_langchain(norm, client)
                    self._mcp[prefixed] = lc_tool
                    self._normalized[prefixed] = norm
                    count += 1
                    # alias with underscore for LLM compatibility (test.lookup -> test_lookup)
                    alias = f"{name}_{raw_name}"
                    if alias not in self._native and alias not in self._mcp:
                        alias_norm = norm.model_copy(update={"name": alias})
                        # adapter for alias should still call original prefixed tool
                        alias_tool = mcp_tool_to_langchain(alias_norm, client)
                        # patch alias tool to call original name
                        orig_prefixed = prefixed
                        orig_client = client
                        def _alias_fn_factory(orig=orig_prefixed, cl=orig_client):
                            def _fn(**kwargs):
                                clean = {k: v for k, v in kwargs.items() if v is not None}
                                return cl.call_tool(orig, clean)
                            return _fn
                        # recreate with correct function
                        from mcp_layer.adapter import _json_schema_to_pydantic as _to_pyd
                        schema = norm.input_schema or {}
                        args_model = _to_pyd(alias, schema)
                        from langchain_core.tools import StructuredTool
                        alias_tool = StructuredTool.from_function(
                            func=_alias_fn_factory(),
                            name=alias, description=norm.description, args_schema=args_model,
                        )
                        alias_tool.metadata = {"source": "mcp", "server": name, "operation": norm.operation, "risk_level": norm.risk_level, "requires_confirmation": norm.requires_confirmation}  # type: ignore
                        self._mcp[alias] = alias_tool
                        self._normalized[alias] = alias_norm
                        count += 1
                    # observability: MCP_TOOL_DISCOVERED will be emitted by caller
                logger.info(f"MCP discovered {len(tools)} tools from server {name} -> {count} registered")
            except MCPError as e:
                logger.warning(f"MCP discover failed for server {name}: {e.code}: {e}")
            except Exception as e:
                logger.warning(f"MCP discover failed for server {name}: {e}")
        self._discovered = True
        return count

    # ---- query ----

    def list_tools(self) -> list:
        return list(self._native.values()) + list(self._mcp.values())

    def all_tools(self) -> list:
        return self.list_tools()

    def valid_names(self) -> list[str]:
        return list(self._native.keys()) + list(self._mcp.keys())

    def get(self, name: str):
        return self._native.get(name) or self._mcp.get(name)

    def tool_map(self) -> dict[str, Any]:
        return {**self._native, **self._mcp}

    def is_mcp_tool(self, name: str) -> bool:
        return name in self._mcp

    def get_normalized(self, name: str) -> Optional[NormalizedTool]:
        return self._normalized.get(name)

    def requires_confirmation(self, tool_name: str, arguments: dict | None = None) -> bool:
        norm = self.get_normalized(tool_name)
        if not norm:
            return False
        return bool(norm.requires_confirmation)

    def tool_info(self) -> str:
        lines = []
        for t in self.list_tools():
            # build similar to planner's TOOL_INFO
            try:
                schema = t.args_schema.model_json_schema() if getattr(t, "args_schema", None) else {}
            except Exception:
                schema = {}
            lines.append(f"- {t.name}: {t.description}\n  Schema: {json.dumps(schema)[:500]}")
        return "\n".join(lines)

    def filtered_tool_info(self, allowed_names: list[str] | set[str] | None = None) -> str:
        if not allowed_names:
            return self.tool_info()
        allowed = set(allowed_names)
        lines = []
        for t in self.list_tools():
            if t.name in allowed:
                try:
                    schema = t.args_schema.model_json_schema() if getattr(t, "args_schema", None) else {}
                except Exception:
                    schema = {}
                lines.append(f"- {t.name}: {t.description}\n  Schema: {json.dumps(schema)[:500]}")
        return "\n".join(lines) if lines else self.tool_info()

    def reset(self) -> None:
        """Clear MCP tools (for tests). Keeps native."""
        self._mcp.clear()
        # remove normalized mcp entries
        for k in list(self._normalized.keys()):
            if self._normalized[k].source == "mcp":
                del self._normalized[k]
        self._clients.clear()
        self._servers.clear()
        self._discovered = False


# global singleton
registry = ToolRegistry()
