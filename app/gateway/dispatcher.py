"""Tool Dispatcher & Capability Gateway with strict schema and approval gates."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.context import ExecutionContext
from app.gateway.approval import approval_engine
from app.gateway.manifest import (
    ApprovalRequirement,
    SideEffectLevel,
    ToolErrorCode,
    ToolManifest,
    ToolResultEnvelope,
)
from app.observability.sink import emit_event

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """
    Centralized Gateway for executing all internal and external tools.
    Enforces typed schema validation, explicit capability classification,
    and cryptographic human confirmation gating.
    """

    def __init__(self):
        self._tools: Dict[str, Tuple[ToolManifest, Callable]] = {}

    def register_tool(self, manifest: ToolManifest, handler: Callable) -> None:
        """Register a tool with its capability manifest and handler function."""
        self._tools[manifest.name] = (manifest, handler)
        logger.debug("Registered tool: %s (%s)", manifest.name, manifest.side_effect.value)

    def get_manifest(self, tool_name: str) -> Optional[ToolManifest]:
        """Lookup manifest by name."""
        entry = self._tools.get(tool_name)
        return entry[0] if entry else None

    def list_manifests(self) -> List[ToolManifest]:
        """Return all registered tool manifests."""
        return [entry[0] for entry in self._tools.values()]

    def dispatch(
        self,
        ctx: ExecutionContext,
        tool_name: str,
        arguments: Dict[str, Any],
        approval_token: Optional[str] = None,
    ) -> ToolResultEnvelope:
        """
        Execute a tool call behind deterministic validation and safety gates.
        """
        t0 = time.perf_counter()
        entry = self._tools.get(tool_name)
        if not entry:
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.RESOURCE_NOT_FOUND,
                error_message=f"Tool '{tool_name}' is not registered in the Tool Gateway.",
            )

        manifest, handler = entry
        args = dict(arguments or {})

        # 1. Strict Schema Validation (No heuristic guessing)
        schema = manifest.input_schema
        required_fields = schema.get("required", []) if isinstance(schema, dict) else []
        missing = [k for k in required_fields if k not in args or args[k] is None]
        if missing:
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.VALIDATION_ERROR,
                error_message=f"Validation error for '{tool_name}': missing required fields {missing}.",
            )

        # 2. Human Approval Gating
        requires_approval = manifest.approval == ApprovalRequirement.ALWAYS or (
            manifest.approval == ApprovalRequirement.CONDITIONAL
            and manifest.side_effect in (SideEffectLevel.DESTRUCTIVE, SideEffectLevel.IRREVERSIBLE_WRITE)
        )

        if requires_approval:
            if not approval_token:
                # Stage approval intent and pause
                summary = f"Execute action '{tool_name}' with parameters {args}"
                action_id, token = approval_engine.stage_approval(
                    ctx=ctx,
                    tool_name=tool_name,
                    arguments=args,
                    summary=summary,
                    risk_level=manifest.side_effect,
                )
                emit_event(
                    ctx=ctx,
                    component="gateway",
                    event_type="APPROVAL_REQUIRED",
                    payload={"action_id": action_id, "tool": tool_name, "args": args},
                )
                return ToolResultEnvelope.awaiting_approval(
                    tool_name=tool_name,
                    approval_token=token,
                    summary=summary,
                    data={"action_id": action_id, "arguments": args},
                )
            else:
                # Validate and consume token
                is_authorized, authorized_tool, authorized_args = approval_engine.validate_and_consume(
                    ctx=ctx,
                    approval_token=approval_token,
                    decision="APPROVE",
                )
                if not is_authorized or authorized_tool != tool_name:
                    return ToolResultEnvelope.error(
                        tool_name=tool_name,
                        error_code=ToolErrorCode.PERMISSION_DENIED,
                        error_message="Action denied: approval token is invalid, expired, or already consumed.",
                    )
                # Enforce execution with the exact authorized arguments (preventing TOCTOU tampering)
                args = authorized_args or args

        # 3. Execution
        try:
            emit_event(
                ctx=ctx,
                component="gateway",
                event_type="TOOL_CALLED",
                payload={"tool": tool_name, "args": args},
            )
            raw_res = handler(ctx=ctx, **args)
            dur_ms = int((time.perf_counter() - t0) * 1000)

            # Wrap in dictionary if scalar
            data_dict = raw_res if isinstance(raw_res, dict) else {"result": raw_res}

            emit_event(
                ctx=ctx,
                component="gateway",
                event_type="TOOL_COMPLETED",
                payload={"tool": tool_name, "duration_ms": dur_ms},
                duration_ms=dur_ms,
            )
            return ToolResultEnvelope.success(
                tool_name=tool_name,
                data=data_dict,
                duration_ms=dur_ms,
            )
        except Exception as e:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            logger.error("Error executing %s: %s", tool_name, e, exc_info=True)
            emit_event(
                ctx=ctx,
                component="gateway",
                event_type="TOOL_FAILED",
                payload={"tool": tool_name, "error": str(e)},
                duration_ms=dur_ms,
                error_details={"exception": type(e).__name__, "message": str(e)},
            )
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.INTERNAL_ERROR,
                error_message=f"Execution of '{tool_name}' failed: {e}",
                duration_ms=dur_ms,
            )


# Global default gateway instance
gateway = ToolDispatcher()
