"""Tool Dispatcher & Capability Gateway with strict schema and approval gates."""

from __future__ import annotations

import logging
import re
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


def validate_schema_arguments(
    schema: Dict[str, Any],
    arguments: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Perform structural validation against tool manifest schema.
    Validates required fields, types, and rejects unknown properties when properties are defined.
    """
    if not schema:
        return True, None

    required = schema.get("required", [])
    missing = [field for field in required if field not in arguments or arguments[field] is None]
    if missing:
        return False, f"missing required fields {missing}"

    properties = schema.get("properties")
    allow_extra = schema.get("additionalProperties", True if not properties else False)

    if properties:
        for key, val in arguments.items():
            if key not in properties:
                if not allow_extra:
                    return False, f"Unexpected/unsupported argument '{key}'"
                continue

            prop_schema = properties[key]
            expected_type = prop_schema.get("type")
            if expected_type == "string" and not isinstance(val, str):
                return False, f"Argument '{key}' must be a string, got {type(val).__name__}"
            elif expected_type == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
                return False, f"Argument '{key}' must be an integer, got {type(val).__name__}"
            elif expected_type == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
                return False, f"Argument '{key}' must be a number, got {type(val).__name__}"
            elif expected_type == "boolean" and not isinstance(val, bool):
                return False, f"Argument '{key}' must be a boolean, got {type(val).__name__}"
            elif expected_type == "array" and not isinstance(val, list):
                return False, f"Argument '{key}' must be an array/list, got {type(val).__name__}"
            elif expected_type == "object" and not isinstance(val, dict):
                return False, f"Argument '{key}' must be an object/dict, got {type(val).__name__}"

            # String constraints
            if isinstance(val, str):
                min_len = prop_schema.get("minLength")
                if min_len is not None and len(val) < min_len:
                    return False, f"Argument '{key}' length must be >= {min_len}"
                max_len = prop_schema.get("maxLength")
                if max_len is not None and len(val) > max_len:
                    return False, f"Argument '{key}' length must be <= {max_len}"
                pattern = prop_schema.get("pattern")
                if pattern and not re.match(pattern, val):
                    return False, f"Argument '{key}' does not match pattern {pattern}"

    return True, None


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
        action_id: Optional[str] = None,
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
                side_effect_occurred=False,
            )

        manifest, handler = entry
        args = dict(arguments or {})

        # 1. Strict Schema Validation (No heuristic guessing)
        is_valid, validation_err = validate_schema_arguments(manifest.input_schema, args)
        if not is_valid:
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.VALIDATION_ERROR,
                error_message=f"Validation error for '{tool_name}': {validation_err}",
                side_effect_occurred=False,
            )

        # 2. Human Approval Gating
        requires_approval = manifest.approval == ApprovalRequirement.ALWAYS or (
            manifest.approval == ApprovalRequirement.CONDITIONAL
            and manifest.side_effect in (SideEffectLevel.DESTRUCTIVE, SideEffectLevel.IRREVERSIBLE_WRITE)
        )

        staged_action_id: Optional[str] = None
        if requires_approval:
            if not approval_token:
                # Stage approval intent and pause
                summary = f"Execute action '{tool_name}' with parameters {args}"
                act_id, token = approval_engine.stage_approval(
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
                    payload={"action_id": act_id, "tool": tool_name, "args": args},
                )
                return ToolResultEnvelope.awaiting_approval(
                    tool_name=tool_name,
                    approval_token=token,
                    summary=summary,
                    data={"action_id": act_id, "arguments": args},
                )
            else:
                # Validate and consume token
                is_authorized, authorized_tool, authorized_args = approval_engine.validate_and_consume(
                    ctx=ctx,
                    approval_token=approval_token,
                    decision="APPROVE",
                    action_id=action_id,
                )
                if not is_authorized or authorized_tool != tool_name:
                    return ToolResultEnvelope.error(
                        tool_name=tool_name,
                        error_code=ToolErrorCode.PERMISSION_DENIED,
                        error_message="Action denied: approval token is invalid, expired, already consumed, or parameter mismatch.",
                        side_effect_occurred=False,
                    )
                # Enforce execution with the exact authorized arguments (preventing TOCTOU tampering)
                args = authorized_args or args
                staged_action_id = action_id or approval_engine.get_action_id_by_token(approval_token)

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

            # Check if returned result represents an error (do NOT wrap error strings as success)
            if isinstance(raw_res, str):
                lower_str = raw_res.lower()
                if any(lower_str.startswith(err_pfx) for err_pfx in ["error", "fetch error", "network error", "http error", "access denied"]):
                    if staged_action_id:
                        approval_engine.record_execution_outcome(staged_action_id, "FAILED", raw_res)
                    return ToolResultEnvelope.error(
                        tool_name=tool_name,
                        error_code=ToolErrorCode.EXTERNAL_SERVICE_ERROR,
                        error_message=raw_res,
                        duration_ms=dur_ms,
                        side_effect_occurred=False,
                    )
                data_dict = {"result": raw_res}
            elif isinstance(raw_res, dict):
                if "error" in raw_res:
                    err_msg = str(raw_res["error"])
                    if staged_action_id:
                        approval_engine.record_execution_outcome(staged_action_id, "FAILED", err_msg)
                    return ToolResultEnvelope.error(
                        tool_name=tool_name,
                        error_code=ToolErrorCode.RESOURCE_NOT_FOUND if "not found" in err_msg.lower() else ToolErrorCode.EXTERNAL_SERVICE_ERROR,
                        error_message=err_msg,
                        duration_ms=dur_ms,
                        side_effect_occurred=False,
                    )
                data_dict = raw_res
            else:
                data_dict = {"result": raw_res}

            if staged_action_id:
                approval_engine.record_execution_outcome(staged_action_id, "SUCCESS")

            # Determine genuine side effect outcome: must be mutating capability and not a reported no-op
            if manifest.side_effect == SideEffectLevel.READ_ONLY:
                actual_side_effect = False
            else:
                if (
                    data_dict.get("deleted") is False
                    or data_dict.get("completed") is False
                    or data_dict.get("created") is False
                    or data_dict.get("updated") is False
                ):
                    actual_side_effect = False
                else:
                    actual_side_effect = True

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
                side_effect_occurred=actual_side_effect,
            )

        except PermissionError as pe:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            if staged_action_id:
                approval_engine.record_execution_outcome(staged_action_id, "FAILED", str(pe))
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.PERMISSION_DENIED,
                error_message=str(pe),
                duration_ms=dur_ms,
            )
        except FileNotFoundError as fe:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            if staged_action_id:
                approval_engine.record_execution_outcome(staged_action_id, "FAILED", str(fe))
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.RESOURCE_NOT_FOUND,
                error_message=str(fe),
                duration_ms=dur_ms,
            )
        except ValueError as ve:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            if staged_action_id:
                approval_engine.record_execution_outcome(staged_action_id, "FAILED", str(ve))
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.VALIDATION_ERROR,
                error_message=str(ve),
                duration_ms=dur_ms,
            )
        except TimeoutError as te:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            is_read_only = (manifest.side_effect == SideEffectLevel.READ_ONLY)
            if staged_action_id:
                approval_engine.record_execution_outcome(
                    staged_action_id,
                    "FAILED" if is_read_only else "UNCERTAIN",
                    str(te),
                )
            return ToolResultEnvelope.error(
                tool_name=tool_name,
                error_code=ToolErrorCode.EXECUTION_TIMEOUT,
                error_message=str(te),
                retryable=True,
                side_effect_occurred=False if is_read_only else None,
                duration_ms=dur_ms,
            )
        except Exception as e:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            logger.error("Error executing %s: %s", tool_name, e, exc_info=True)
            is_read_only = (manifest.side_effect == SideEffectLevel.READ_ONLY)
            if staged_action_id:
                approval_engine.record_execution_outcome(
                    staged_action_id,
                    "FAILED" if is_read_only else "UNCERTAIN",
                    str(e),
                )
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
                side_effect_occurred=False if is_read_only else None,
                duration_ms=dur_ms,
            )


# Global default gateway instance
gateway = ToolDispatcher()
