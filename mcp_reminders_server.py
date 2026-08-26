#!/usr/bin/env python
"""
Reminders MCP server — deterministic local JSON backend.
Tools: create, list, get, complete, delete
"""

import json
from pathlib import Path
from mcp.server.mcpserver import MCPServer

DATA = Path(__file__).resolve().parent / "mcp_data"
DATA.mkdir(exist_ok=True)
DB = DATA / "reminders.json"

mcp = MCPServer(name="reminders", version="1.0.0")


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
async def create(text: str, when: str = "") -> str:
    """Create a reminder. Returns the reminder id."""
    import json as _json
    d = _load()
    rid = f"rem_{len(d.get('reminders', {})) + 1:03d}"
    d.setdefault("reminders", {})[rid] = {"text": text, "when": when, "done": False}
    _save(d)
    return _json.dumps({"reminder_id": rid, "text": text, "when": when})


@mcp.tool()
async def list(done: str = "") -> str:
    """List reminders. done='true'/'false' filters by state; empty lists all."""
    import json as _json
    d = _load()
    out = []
    for rid, r in d.get("reminders", {}).items():
        if done == "true" and not r.get("done"):
            continue
        if done == "false" and r.get("done"):
            continue
        out.append({"reminder_id": rid, **r})
    return _json.dumps(out)


@mcp.tool()
async def get(reminder_id: str) -> str:
    """Get a single reminder by id."""
    import json as _json
    d = _load()
    r = d.get("reminders", {}).get(reminder_id)
    if not r:
        raise ValueError(f"Reminder not found: {reminder_id}")
    return _json.dumps({"reminder_id": reminder_id, **r})


@mcp.tool()
async def complete(reminder_id: str) -> str:
    """Mark a reminder as done."""
    d = _load()
    r = d.get("reminders", {}).get(reminder_id)
    if not r:
        raise ValueError(f"Reminder not found: {reminder_id}")
    r["done"] = True
    _save(d)
    return f"Completed {reminder_id}"


@mcp.tool()
async def delete(reminder_id: str) -> str:
    """Delete a reminder by id."""
    d = _load()
    rems = d.get("reminders", {})
    if reminder_id not in rems:
        raise ValueError(f"Reminder not found: {reminder_id}")
    del rems[reminder_id]
    _save(d)
    return f"Deleted {reminder_id}"


if __name__ == "__main__":
    import anyio
    anyio.run(mcp.run_stdio_async)
