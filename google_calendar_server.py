#!/usr/bin/env python
"""Google Calendar MCP server scaffold.

This is a real Google Calendar adapter that follows the same MCP pattern as the
local JSON-based calendar server in this repo. To use it, configure OAuth
credentials and add it to the MCP registry.

Required environment variables:
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
- GOOGLE_TOKEN_FILE (default: .google_token.json)
- GOOGLE_CREDENTIALS_FILE (optional if using OAuth JSON file)

This scaffold exposes a minimal, production-friendly tool set:
- list_events
- get_event
- create_event
- update_event
- delete_event
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="google_calendar", version="1.0.0")

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
DEFAULT_TOKEN_FILE = Path(os.getenv("GOOGLE_TOKEN_FILE", ".google_token.json"))
if not DEFAULT_TOKEN_FILE.is_absolute():
    DEFAULT_TOKEN_FILE = PROJECT_ROOT / DEFAULT_TOKEN_FILE
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")
if CREDENTIALS_FILE and not Path(CREDENTIALS_FILE).is_absolute():
    CREDENTIALS_FILE = str(PROJECT_ROOT / CREDENTIALS_FILE)
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


def _get_credentials() -> Credentials:
    """Return OAuth credentials for the Google Calendar API."""
    creds = None
    if os.path.exists(DEFAULT_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(DEFAULT_TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_ID or not CLIENT_SECRET:
                raise RuntimeError(
                    "Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET. "
                    "Create OAuth credentials in Google Cloud Console and set them in the environment."
                )
            if not CREDENTIALS_FILE:
                raise RuntimeError(
                    "Missing GOOGLE_CREDENTIALS_FILE. Provide the OAuth client JSON downloaded from Google Cloud."
                )
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as credentials_file:
                client_config = json.load(credentials_file)
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(DEFAULT_TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def _calendar_service():
    creds = _get_credentials()
    return build("calendar", "v3", credentials=creds)


@mcp.tool()
async def list_events(
    calendar_id: str = "primary",
    max_results: int = 20,
    query: str = "",
    start_date: str = "",
    end_date: str = "",
) -> str:
    """List Google Calendar events.

    Args:
        calendar_id: Calendar ID, usually 'primary'.
        max_results: Max number of items to return.
        query: Free-text search term.
        start_date: Optional ISO date string: YYYY-MM-DD.
        end_date: Optional ISO date string: YYYY-MM-DD.
    """
    try:
        service = _calendar_service()
        now = datetime.utcnow()
        start = datetime.fromisoformat(start_date) if start_date else now - timedelta(days=7)
        end = datetime.fromisoformat(end_date) if end_date else now + timedelta(days=30)

        time_min = start.isoformat() + "Z" if start_date else now.isoformat() + "Z"
        time_max = end.isoformat() + "Z" if end_date else (now + timedelta(days=30)).isoformat() + "Z"

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_results,
            q=query,
        ).execute()
        events = events_result.get("items", [])
        return json.dumps(events, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover - runtime integration path
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_event(event_id: str, calendar_id: str = "primary") -> str:
    """Get a single event by ID."""
    try:
        service = _calendar_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return json.dumps(event, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> str:
    """Create a Google Calendar event.

    Args:
        title: Event title.
        start_time: ISO datetime string, e.g. 2026-09-20T09:00:00.
        end_time: ISO datetime string, e.g. 2026-09-20T10:00:00.
    """
    try:
        service = _calendar_service()
        event = {
            "summary": title,
            "location": location,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": "UTC"},
            "end": {"dateTime": end_time, "timeZone": "UTC"},
        }
        created = service.events().insert(calendarId=calendar_id, body=event).execute()
        return json.dumps(created, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def update_event(
    event_id: str,
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> str:
    """Update an existing event by ID."""
    try:
        service = _calendar_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        if title:
            event["summary"] = title
        if start_time:
            event["start"] = {"dateTime": start_time, "timeZone": "UTC"}
        if end_time:
            event["end"] = {"dateTime": end_time, "timeZone": "UTC"}
        if description:
            event["description"] = description
        if location:
            event["location"] = location

        updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
        return json.dumps(updated, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def delete_event(event_id: str, calendar_id: str = "primary") -> str:
    """Delete a Google Calendar event."""
    try:
        service = _calendar_service()
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return json.dumps({"status": "deleted", "event_id": event_id, "calendar_id": calendar_id})
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    anyio.run(mcp.run_stdio_async)
