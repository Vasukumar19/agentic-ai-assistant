"""Local Calendar Service providing tenant-isolated schedule data and Google Calendar bridge."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.context import ExecutionContext

logger = logging.getLogger(__name__)


class LocalCalendarService:
    """
    Manages calendar commitments and event schedules.
    Provides local-first tenant-isolated event storage and read-only Google Calendar integration.
    """

    def __init__(self):
        # In-memory tenant event registry: user_id -> Dict[event_id, event_dict]
        self._user_events: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def seed_events_for_user(self, user_id: str, events: Dict[str, Dict[str, Any]]) -> None:
        """Seed calendar events for a specific user (used by test adapters and initial setups)."""
        self._user_events[user_id] = dict(events)

    def list_events(self, ctx: ExecutionContext, target_date: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """List calendar events for tenant, optionally filtered by date."""
        user_store = self._user_events.get(ctx.user_id, {})
        if not user_store and ctx.user_id in ("usr_default", "usr_dev"):
            # Provide standard baseline calendar schedule for default local workspace
            user_store = {
                "evt_101": {
                    "title": "Weekly Engineering Sync",
                    "date": "2026-10-14",
                    "time": "10:00",
                    "description": "Team project review and blockers sync",
                    "status": "confirmed",
                },
                "evt_102": {
                    "title": "Architecture Review",
                    "date": "2026-10-14",
                    "time": "10:00",
                    "description": "Conflict slot with weekly sync",
                    "status": "confirmed",
                },
                "evt_103": {
                    "title": "Candidate Tech Interview",
                    "date": "2026-10-14",
                    "time": "11:00",
                    "description": "Interview Senior Backend Engineer candidate",
                    "status": "confirmed",
                },
                "evt_104": {
                    "title": "Executive 1-on-1",
                    "date": "2026-10-14",
                    "time": "15:00",
                    "description": "Quarterly planning and review with VP",
                    "status": "confirmed",
                },
            }
            self._user_events[ctx.user_id] = user_store

        if target_date:
            return {k: v for k, v in user_store.items() if v.get("date") == target_date}
        return dict(user_store)

    def get_event(self, ctx: ExecutionContext, event_id: str) -> Optional[Dict[str, Any]]:
        """Lookup a specific event by ID for tenant."""
        user_store = self._user_events.get(ctx.user_id, {})
        if not user_store and ctx.user_id in ("usr_default", "usr_dev"):
            self.list_events(ctx)
            user_store = self._user_events.get(ctx.user_id, {})
        return user_store.get(event_id)


# Global default calendar service instance
calendar_service = LocalCalendarService()
