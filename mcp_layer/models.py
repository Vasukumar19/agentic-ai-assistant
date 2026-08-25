"""Normalized tool and server models for MCP."""

from __future__ import annotations

from typing import Any, Optional, Literal
from pydantic import BaseModel, Field


Operation = Literal["read", "write", "destructive"]
RiskLevel = Literal["low", "medium", "high"]
Source = Literal["native", "mcp"]


class NormalizedTool(BaseModel):
    """Internal normalized representation — every tool, native or MCP, becomes this."""
    name: str = Field(description="Globally unique name, e.g. calculator or calendar.search")
    description: str = Field(default="")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON schema for arguments")
    source: Source = Field(description="native or mcp")
    server: Optional[str] = Field(default=None, description="MCP server name if source=mcp")
    operation: Operation = Field(default="read")
    risk_level: RiskLevel = Field(default="low")
    requires_confirmation: bool = Field(default=False)
    timeout_s: float = Field(default=15.0)
    enabled: bool = Field(default=True)
    # original MCP name before prefixing, for debugging
    original_name: Optional[str] = None


class MCPServerConfig(BaseModel):
    """Configuration for one MCP server — externalized, no secrets in code."""
    name: str = Field(description="Logical server name, e.g. test, calendar")
    transport: Literal["stdio", "http", "streamable_http"] = Field(default="stdio")
    # stdio
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    # http
    url: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    # common
    enabled: bool = True
    timeout_s: float = 15.0
    # policy overrides: tool_name -> {operation, risk_level, requires_confirmation}
    tool_policy: dict[str, dict[str, Any]] = Field(default_factory=dict)
