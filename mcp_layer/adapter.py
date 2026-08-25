"""MCP → LangChain adapter — turns a normalized MCP tool into a LangChain StructuredTool."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from .models import NormalizedTool

logger = logging.getLogger(__name__)


def _json_schema_to_pydantic(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Convert JSON schema properties to a Pydantic model for StructuredTool."""
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    required = set(schema.get("required", []) or [])
    fields: dict[str, Any] = {}
    type_map = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}
    for pname, pspec in props.items():
        ptype = pspec.get("type", "string") if isinstance(pspec, dict) else "string"
        py_type = type_map.get(ptype, str)
        desc = pspec.get("description", "") if isinstance(pspec, dict) else ""
        if pname in required:
            fields[pname] = (py_type, Field(description=desc))
        else:
            fields[pname] = (py_type, Field(default=None, description=desc))
    if not fields:
        # fallback: single generic input
        fields["input"] = (str, Field(default=None, description="input"))
    try:
        return create_model(f"{name}Input", **fields)
    except Exception:
        # fallback minimal
        class _Generic(BaseModel):
            input: str | None = Field(default=None, description="input")
        return _Generic


def mcp_tool_to_langchain(normalized: NormalizedTool, client) -> StructuredTool:
    """Create a LangChain StructuredTool that delegates to MCP client."""
    schema = normalized.input_schema or {}
    args_model = _json_schema_to_pydantic(normalized.name.replace(".", "_"), schema)

    def _fn(**kwargs) -> str:
        # filter None values that were optional but not provided
        clean = {k: v for k, v in kwargs.items() if v is not None}
        # StructuredTool will pass kwargs matching schema
        return client.call_tool(normalized.name, clean, timeout_s=normalized.timeout_s)

    # StructuredTool.from_function requires func with proper signature; use args_schema instead
    tool = StructuredTool.from_function(
        func=lambda **kwargs: _fn(**kwargs),
        name=normalized.name,
        description=normalized.description or f"MCP tool {normalized.name} via {normalized.server}",
        args_schema=args_model,
    )
    # stash metadata for registry/tracing
    tool.metadata = {  # type: ignore
        "source": "mcp",
        "server": normalized.server,
        "operation": normalized.operation,
        "risk_level": normalized.risk_level,
        "requires_confirmation": normalized.requires_confirmation,
    }
    return tool
