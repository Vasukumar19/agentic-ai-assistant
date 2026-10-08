"""SQLite Database Model Context Protocol (MCP) Server.

Standard MCP stdio server providing SQLite database tool capabilities:
- sqlite.list_tables
- sqlite.describe_table
- sqlite.read_query
- sqlite.create_record
- sqlite.delete_record

Operates on a sandboxed local SQLite database file (mcp_sandbox/app.db).
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any
import anyio
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="sqlite", version="1.0.0")

SANDBOX_DIR = Path(__file__).resolve().parent / "mcp_sandbox"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SANDBOX_DIR / "app.db"


def _init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _deleted_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            deleted_at TEXT NOT NULL
        )
    """)
    cursor.execute("SELECT count(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO users (name, email, role) VALUES (?, ?, ?)", [
            ("Alice Smith", "alice@example.com", "admin"),
            ("Bob Jones", "bob@example.com", "developer"),
            ("Charlie Brown", "charlie@example.com", "analyst"),
        ])
    conn.commit()
    conn.close()


_init_db()


@mcp.tool()
async def list_tables() -> str:
    """List all user tables in the SQLite database."""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return json.dumps(tables, ensure_ascii=False)


@mcp.tool()
async def describe_table(table_name: str) -> str:
    """Get the column definitions and schema for a specific table.

    Args:
        table_name: Table name to inspect
    """
    if not table_name:
        return "Error: table_name parameter is required"
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    cols = cursor.fetchall()
    conn.close()
    if not cols:
        return f"Error: Table not found: {table_name}"
    schema = [{"cid": c[0], "name": c[1], "type": c[2], "notnull": c[3], "pk": c[5]} for c in cols]
    return json.dumps(schema, ensure_ascii=False)


@mcp.tool()
async def read_query(query: str) -> str:
    """Execute a read-only SELECT SQL query on the database.

    Args:
        query: SELECT SQL query
    """
    if not query:
        return "Error: query parameter is required"
    trimmed = query.strip()
    if not trimmed.lower().startswith("select"):
        return "Error: read_query only allows SELECT statements"
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(trimmed)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return json.dumps(rows, ensure_ascii=False)
    except Exception as e:
        conn.close()
        return f"Error: SQL execution failed: {e}"


@mcp.tool()
async def create_record(table_name: str, data: str) -> str:
    """Insert a new record into a table.

    Args:
        table_name: Table name
        data: JSON string representing column-value pairs
    """
    if not table_name:
        return "Error: table_name parameter is required"
    if not data:
        return "Error: data parameter is required"
    try:
        parsed = json.loads(data) if isinstance(data, str) else data
    except Exception:
        return f"Error: invalid JSON in data: {data}"
    
    keys = list(parsed.keys())
    values = [parsed[k] for k in keys]
    placeholders = ", ".join(["?"] * len(keys))
    cols = ", ".join(keys)

    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT OR REPLACE INTO {table_name} ({cols}) VALUES ({placeholders})", values)
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return json.dumps({"status": "created", "id": new_id, "table": table_name, "record": parsed}, ensure_ascii=False)
    except Exception as e:
        conn.close()
        return json.dumps({"error": f"Failed to insert into {table_name}: {e}"}, ensure_ascii=False)


@mcp.tool()
async def delete_record(table_name: str, record_id: int) -> str:
    """Delete a record from a table by ID (saved to rollback stage for undo).

    Args:
        table_name: Table name
        record_id: Integer primary key ID
    """
    if not table_name:
        return "Error: table_name parameter is required"
    if record_id is None:
        return "Error: record_id parameter is required"
    import datetime
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # Fetch existing record for rollback staging
        cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return f"Error: Record with ID {record_id} not found in {table_name}"
        
        row_data = json.dumps(dict(row), ensure_ascii=False)
        now_iso = datetime.datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO _deleted_records (table_name, record_id, data, deleted_at) VALUES (?, ?, ?, ?)",
            (table_name, record_id, row_data, now_iso)
        )
        cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        return json.dumps({"status": "deleted", "id": record_id, "table": table_name, "undo_available": True}, ensure_ascii=False)
    except Exception as e:
        conn.close()
        return f"Error: Failed to delete from {table_name}: {e}"


@mcp.tool()
async def undo_delete(table_name: str = "", record_id: int = 0) -> str:
    """Restore the most recently deleted record (or matching specific table and record_id).

    Args:
        table_name: Optional table name to filter
        record_id: Optional record ID to restore
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        query = "SELECT * FROM _deleted_records"
        params = []
        conds = []
        if table_name:
            conds.append("table_name = ?")
            params.append(table_name)
        if record_id:
            conds.append("record_id = ?")
            params.append(record_id)
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY id DESC LIMIT 1"
        
        cursor.execute(query, tuple(params))
        stage_row = cursor.fetchone()
        if not stage_row:
            conn.close()
            return "Error: No deleted records found to restore."
        
        del_id = stage_row["id"]
        t_name = stage_row["table_name"]
        rec_data = json.loads(stage_row["data"])
        
        cols = ", ".join(rec_data.keys())
        placeholders = ", ".join(["?"] * len(rec_data))
        values = list(rec_data.values())
        
        cursor.execute(f"INSERT OR REPLACE INTO {t_name} ({cols}) VALUES ({placeholders})", values)
        cursor.execute("DELETE FROM _deleted_records WHERE id = ?", (del_id,))
        conn.commit()
        conn.close()
        return json.dumps({"status": "restored", "table": t_name, "record": rec_data}, ensure_ascii=False)
    except Exception as e:
        conn.close()
        return f"Error: Failed to restore record: {e}"


if __name__ == "__main__":
    anyio.run(mcp.run_stdio_async)
