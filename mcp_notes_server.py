#!/usr/bin/env python
"""
Notes MCP server — deterministic local JSON backend.
Tools: create, list, read, update, delete
"""

import json
from pathlib import Path
from mcp.server.mcpserver import MCPServer

DATA = Path(__file__).resolve().parent / "mcp_data"
DATA.mkdir(exist_ok=True)
DB = DATA / "notes.json"

mcp = MCPServer(name="notes", version="1.0.0")


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
async def create(title: str, content: str) -> str:
    """Create a note. Returns the note id."""
    import json as _json
    d = _load()
    nid = f"note_{len(d.get('notes', {})) + 1:03d}"
    d.setdefault("notes", {})[nid] = {"title": title, "content": content}
    _save(d)
    return _json.dumps({"note_id": nid, "title": title})


@mcp.tool()
async def list(query: str = "") -> str:
    """List notes (id + title), optionally filtered by title substring."""
    import json as _json
    d = _load()
    out = []
    for nid, n in d.get("notes", {}).items():
        if query and query.lower() not in n.get("title", "").lower():
            continue
        out.append({"note_id": nid, "title": n["title"]})
    return _json.dumps(out)


@mcp.tool()
async def read(note_id: str) -> str:
    """Read full note content by id."""
    d = _load()
    n = d.get("notes", {}).get(note_id)
    if not n:
        raise ValueError(f"Note not found: {note_id}")
    return f"[{n['title']}]\n{n['content']}"


@mcp.tool()
async def update(note_id: str, title: str = "", content: str = "") -> str:
    """Update an existing note."""
    d = _load()
    n = d.get("notes", {}).get(note_id)
    if not n:
        raise ValueError(f"Note not found: {note_id}")
    if title:
        n["title"] = title
    if content:
        n["content"] = content
    _save(d)
    return f"Updated {note_id}"


@mcp.tool()
async def delete(note_id: str) -> str:
    """Delete a note by id."""
    d = _load()
    notes = d.get("notes", {})
    if note_id not in notes:
        raise ValueError(f"Note not found: {note_id}")
    del notes[note_id]
    _save(d)
    return f"Deleted {note_id}"


if __name__ == "__main__":
    import anyio
    anyio.run(mcp.run_stdio_async)
