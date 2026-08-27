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
    """Delete a record from a table by ID.

    Args:
        table_name: Table name
        record_id: Integer primary key ID
    """
    if not table_name:
        return "Error: table_name parameter is required"
    if record_id is None:
        return "Error: record_id parameter is required"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected == 0:
            return f"Error: Record with ID {record_id} not found in {table_name}"
        return json.dumps({"status": "deleted", "id": record_id, "table": table_name}, ensure_ascii=False)
    except Exception as e:
        conn.close()
        return f"Error: Failed to delete from {table_name}: {e}"


if __name__ == "__main__":
    anyio.run(mcp.run_stdio_async)
