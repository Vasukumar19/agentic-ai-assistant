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


DEFAULT_NOTES = {
    "notes": {
        "note_001": {"title": "Project Review agenda", "content": "Review Q3 goals and milestones. Date: 2026-09-10"},
        "note_002": {"title": "Meeting Notes Q3", "content": "Discuss engineering roadmap and release plan. Date: 2026-09-12"},
        "note_009": {"title": "Shopping List", "content": "Milk: $3.50, Bread: $2.50, Eggs: $4.00, Butter: $3.00, Apples: $5.00"},
    }
}


def _load() -> dict:
    if DB.exists():
        try:
            d = json.loads(DB.read_text(encoding="utf-8"))
            if d.get("notes"):
                return d
        except Exception:
            pass
    _save(DEFAULT_NOTES)
    return DEFAULT_NOTES


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
    """List notes (id + title), optionally filtered by title or content substring."""
    import json as _json
    d = _load()
    out = []
    for nid, n in d.get("notes", {}).items():
        if query:
            q = query.lower()
            title_match = q in n.get("title", "").lower()
            content_match = q in n.get("content", "").lower()
            if not (title_match or content_match):
                continue
        out.append({"note_id": nid, "title": n["title"]})
    return _json.dumps(out)


@mcp.tool()
async def read(note_id: str) -> str:
    """Read full note content by id."""
    d = _load()
    n = d.get("notes", {}).get(note_id)
    if not n:
        return f"Error: Note not found: {note_id}"
    return f"[{n['title']}]\n{n['content']}"


@mcp.tool()
async def update(note_id: str, title: str = "", content: str = "") -> str:
    """Update an existing note."""
    d = _load()
    n = d.get("notes", {}).get(note_id)
    if not n:
        return f"Error: Note not found: {note_id}"
    if title:
        n["title"] = title
    if content:
        n["content"] = content
    _save(d)
    return f"Updated {note_id}"


@mcp.tool()
async def delete(note_id: str) -> str:
    """Delete a note by id (moved to trash for rollback/undo)."""
    d = _load()
    notes = d.get("notes", {})
    if note_id not in notes:
        return f"Error: Note not found: {note_id}"
    d.setdefault("_trash", {})[note_id] = notes.pop(note_id)
    _save(d)
    return f"Deleted {note_id} (moved to trash, undo available)"


@mcp.tool()
async def undo_delete(note_id: str = "") -> str:
    """Restore a deleted note from trash. If note_id is empty, restores the most recent."""
    import json as _json
    d = _load()
    trash = d.get("_trash", {})
    if not trash:
        return "Error: Trash is empty. No deleted notes to restore."
    target_id = note_id if note_id and note_id in trash else list(trash.keys())[-1]
    restored_note = trash.pop(target_id)
    d.setdefault("notes", {})[target_id] = restored_note
    _save(d)
    return _json.dumps({"status": "restored", "note_id": target_id, "title": restored_note.get("title")})


if __name__ == "__main__":
    import anyio
    anyio.run(mcp.run_stdio_async)
