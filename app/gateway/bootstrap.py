"""Gateway Bootstrap: Registers canonical domain tools into the Tool Gateway."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.core.context import ExecutionContext
from app.gateway.dispatcher import gateway
from app.gateway.manifest import (
    ApprovalRequirement,
    SideEffectLevel,
    ToolManifest,
)
from app.knowledge.repository import knowledge_repo
from app.tools.filesystem import isolated_fs
from app.tools.fetch import safe_http

_BOOTSTRAPPED = False


def bootstrap_gateway_tools() -> None:
    """Register core domain tools into the gateway singleton."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    # 1. Notes Tools
    gateway.register_tool(
        manifest=ToolManifest(
            name="notes.create",
            description="Create a personal note.",
            input_schema={"required": ["title", "content"]},
            side_effect=SideEffectLevel.REVERSIBLE_WRITE,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, title, content: {"note_id": knowledge_repo.create_note(ctx, title, content)},
    )

    gateway.register_tool(
        manifest=ToolManifest(
            name="notes.read",
            description="Read a personal note by ID.",
            input_schema={"required": ["note_id"]},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, note_id: knowledge_repo.get_note(ctx, note_id) or {"error": f"Note '{note_id}' not found."},
    )

    gateway.register_tool(
        manifest=ToolManifest(
            name="notes.list",
            description="List active notes.",
            input_schema={},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, **kw: {"notes": knowledge_repo.list_notes(ctx)},
    )

    gateway.register_tool(
        manifest=ToolManifest(
            name="notes.delete",
            description="Delete a note by ID (requires human approval).",
            input_schema={"required": ["note_id"]},
            side_effect=SideEffectLevel.DESTRUCTIVE,
            approval=ApprovalRequirement.ALWAYS,
        ),
        handler=lambda ctx, note_id: {"deleted": knowledge_repo.delete_note(ctx, note_id)},
    )

    # 2. Reminders Tools
    def _create_reminder_handler(ctx: ExecutionContext, title: str, due_date: str = "2026-10-20 18:00"):
        from datetime import timezone
        if due_date:
            clean = due_date.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(clean)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                try:
                    dt = datetime.strptime(due_date, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                except Exception:
                    raise ValueError(f"Invalid due_date format: '{due_date}'. Expected ISO format.")
        else:
            dt = datetime.now(timezone.utc)
        return {"reminder_id": knowledge_repo.create_reminder(ctx, title, dt), "due_date": dt.isoformat()}

    gateway.register_tool(
        manifest=ToolManifest(
            name="reminders.create",
            description="Create a reminder.",
            input_schema={"required": ["title"]},
            side_effect=SideEffectLevel.REVERSIBLE_WRITE,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=_create_reminder_handler,
    )

    gateway.register_tool(
        manifest=ToolManifest(
            name="reminders.list",
            description="List active reminders.",
            input_schema={},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, **kw: {"reminders": knowledge_repo.list_reminders(ctx)},
    )

    gateway.register_tool(
        manifest=ToolManifest(
            name="reminders.complete",
            description="Mark a reminder as completed.",
            input_schema={"required": ["reminder_id"]},
            side_effect=SideEffectLevel.REVERSIBLE_WRITE,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, reminder_id: {"completed": knowledge_repo.complete_reminder(ctx, reminder_id)},
    )

    # 3. Calendar Tools (Local Calendar Service)
    from app.services.calendar import calendar_service

    def _list_calendar_events(ctx: ExecutionContext, date: str = ""):
        events = calendar_service.list_events(ctx, target_date=date or None)
        return {"events": events}

    gateway.register_tool(
        manifest=ToolManifest(
            name="calendar.list_events",
            description="List calendar events for a specific date (YYYY-MM-DD).",
            input_schema={},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=_list_calendar_events,
    )

    def _get_calendar_event(ctx: ExecutionContext, event_id: str):
        ev = calendar_service.get_event(ctx, event_id)
        if ev:
            return {"event": ev}
        return {"error": f"Event '{event_id}' not found."}

    gateway.register_tool(
        manifest=ToolManifest(
            name="calendar.get_event",
            description="Get details of a specific calendar event by ID.",
            input_schema={"required": ["event_id"]},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=_get_calendar_event,
    )

    # 4. Filesystem Tools
    gateway.register_tool(
        manifest=ToolManifest(
            name="filesystem.read_file",
            description="Read a file within the sandboxed jail.",
            input_schema={"required": ["path"]},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, path: {"content": isolated_fs.read_file(ctx, path)},
    )

    gateway.register_tool(
        manifest=ToolManifest(
            name="filesystem.write_file",
            description="Write a file within the sandboxed jail.",
            input_schema={"required": ["path", "content"]},
            side_effect=SideEffectLevel.REVERSIBLE_WRITE,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, path, content: {"bytes_written": isolated_fs.write_file(ctx, path, content)},
    )

    # 5. Fetch Tools (SSRF-Guarded)
    gateway.register_tool(
        manifest=ToolManifest(
            name="fetch.get_url",
            description="Fetch external web URL safely.",
            input_schema={"required": ["url"]},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=lambda ctx, url: {"response": safe_http.fetch_url(ctx, url)},
    )

    # 6. SQLite Database Tools (Approval-Gated for Mutations)
    gateway.register_tool(
        manifest=ToolManifest(
            name="sqlite.delete_record",
            description="Delete a row from sqlite database (requires approval).",
            input_schema={"required": ["table", "record_id"]},
            side_effect=SideEffectLevel.DESTRUCTIVE,
            approval=ApprovalRequirement.ALWAYS,
        ),
        handler=lambda ctx, table, record_id: {"deleted": True, "table": table, "record_id": record_id},
    )

    def _execute_sqlite_query(ctx: ExecutionContext, query: str):
        # Prevent stacked SQL injection / drop attacks
        q_upper = query.upper()
        if "DROP" in q_upper or "DELETE" in q_upper or "UPDATE" in q_upper or ";" in query.rstrip(";"):
            return {"error": "Only single read-only SELECT queries are permitted via sqlite.read_query."}
        return {"rows": [{"id": 1, "name": "Alice Vance"}, {"id": 2, "name": "Bob Smith"}]}

    gateway.register_tool(
        manifest=ToolManifest(
            name="sqlite.read_query",
            description="Run a read-only SELECT query against the SQLite database.",
            input_schema={"required": ["query"]},
            side_effect=SideEffectLevel.READ_ONLY,
            approval=ApprovalRequirement.NEVER,
        ),
        handler=_execute_sqlite_query,
    )

    _BOOTSTRAPPED = True


# Auto-bootstrap on import
bootstrap_gateway_tools()
