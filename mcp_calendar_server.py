#!/usr/bin/env python
"""
Calendar MCP server — deterministic local JSON backend.
Tools: create_event, list_events, get_event, update_event, delete_event
"""

import json
from pathlib import Path
from mcp.server.mcpserver import MCPServer

DATA = Path(__file__).resolve().parent / "mcp_data"
DATA.mkdir(exist_ok=True)
DB = DATA / "calendar.json"

mcp = MCPServer(name="calendar", version="1.0.0")


def _load() -> dict:
    if DB.exists():
        try:
            return json.loads(DB.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(d: dict) -> None:
    DB.write_text(json.dumps(d, indent=2), encoding="utf-8")


@mcp.tool()
async def create_event(title: str, date: str, time: str = "09:00", description: str = "") -> str:
    """Create a calendar event. Returns the event id."""
    import json as _json
    d = _load()
    eid = f"evt_{len(d.get('events', {})) + 1:03d}"
    d.setdefault("events", {})[eid] = {
        "title": title, "date": date, "time": time,
        "description": description, "status": "confirmed",
    }
    _save(d)
    return _json.dumps({"event_id": eid, "start_time": f"{date} {time}", "title": title})


@mcp.tool()
async def list_events(date: str = "") -> str:
    """List events, optionally filtered by date (YYYY-MM-DD)."""
    import json as _json
    d = _load()
    events = d.get("events", {})
    out = []
    for eid, e in events.items():
        if date and e.get("date") != date:
            continue
        out.append({"event_id": eid, **e})
    return _json.dumps(out)


@mcp.tool()
async def get_event(event_id: str) -> str:
    """Get a single event by id."""
    import json as _json
    d = _load()
    e = d.get("events", {}).get(event_id)
    if not e:
        raise ValueError(f"Event not found: {event_id}")
    return _json.dumps({"event_id": event_id, **e})


@mcp.tool()
async def update_event(event_id: str, title: str = "", date: str = "", time: str = "", description: str = "") -> str:
    """Update an existing event's fields."""
    d = _load()
    e = d.get("events", {}).get(event_id)
    if not e:
        raise ValueError(f"Event not found: {event_id}")
    for k, v in (("title", title), ("date", date), ("time", time), ("description", description)):
        if v:
            e[k] = v
    _save(d)
    return f"Updated {event_id}"


@mcp.tool()
async def delete_event(event_id: str) -> str:
    """Delete an event by id."""
    d = _load()
    events = d.get("events", {})
    if event_id not in events:
        raise ValueError(f"Event not found: {event_id}")
    del events[event_id]
    _save(d)
    return f"Deleted {event_id}"


if __name__ == "__main__":
    import anyio
    anyio.run(mcp.run_stdio_async)
