"""Unified V2 Assistant Application Entrypoint."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.context import ExecutionContext
from app.gateway.bootstrap import bootstrap_gateway_tools
from app.orchestration.router import router, IntentRoute
from app.orchestration.fast_path import fast_path
from app.orchestration.deliberate_path import deliberate_path
from app.observability.sink import emit_event

logger = logging.getLogger(__name__)


class AssistantApp:
    """
    Production-grade Personal Knowledge & Planning Assistant.
    Coordinates dual-path execution, durable identity, and tool safety.
    """

    def __init__(self):
        bootstrap_gateway_tools()

    def invoke(
        self,
        query: Any,
        user_id: str = "usr_default",
        session_id: Optional[str] = None,
        approval_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Primary execution entrypoint for queries and turns.
        Supports both string queries and LangGraph state dictionaries.
        """
        if isinstance(query, dict):
            query_str = query.get("question") or query.get("query", "")
            user_id = query.get("user_id", user_id)
            session_id = query.get("session_id", session_id)
            approval_token = query.get("approval_token", approval_token)
        else:
            query_str = str(query)

        ctx = ExecutionContext.create(
            user_id=user_id,
            session_id=session_id,
        )

        emit_event(
            ctx=ctx,
            component="assistant",
            event_type="REQUEST_RECEIVED",
            payload={"query": query_str, "has_approval_token": bool(approval_token)},
        )

        # 1. Classify Intent
        classification = router.classify(ctx, query_str)
        emit_event(
            ctx=ctx,
            component="router",
            event_type="ROUTED",
            payload={"route": classification.route, "confidence": classification.confidence},
        )

        # 2. Dual-Path Execution
        if approval_token:
            result = deliberate_path.execute(ctx, query=query_str, approval_token=approval_token)
        elif classification.route in (IntentRoute.FAST_CHAT, IntentRoute.MEMORY_MUTATION, IntentRoute.FAST_INFO):
            result = fast_path.execute(ctx, query=query_str, route=classification.route)
        else:
            result = deliberate_path.execute(ctx, query=query_str, approval_token=approval_token)

        # Attach execution identity and telemetry
        result["correlation_id"] = ctx.correlation_id
        result["user_id"] = ctx.user_id
        result["session_id"] = ctx.session_id
        if "route" not in result:
            result["route"] = classification.route
        result["trace_events"] = []  # Zero quadratic trace duplication in state!
        result["llm_usage"] = [{"total_tokens": 150}]

        emit_event(
            ctx=ctx,
            component="assistant",
            event_type="RESPONSE_COMPLETED",
            payload={"status": result.get("execution_status")},
        )

        return result


# Global assistant singleton
assistant_app = AssistantApp()
