# Real-World MCP Application Integration Guide

## 1. Supported Real Applications

The **Agentic AI Assistant** connects to real-world software applications using standard **Model Context Protocol (MCP)** stdio/HTTP servers:

| Application | Server Module | Core Capabilities | Operation Type |
|---|---|---|---|
| **GitHub** | `mcp_github_server.py` | `get_issue`, `list_issues`, `create_issue`, `get_repository`, `search_repositories` | REST / GraphQL API |
| **SQLite Database** | `mcp_sqlite_server.py` | `list_tables`, `describe_table`, `read_query`, `create_record`, `delete_record` | Relational Storage |
| **Web Fetch & API** | `mcp_fetch_server.py` | `get_url`, `get_json`, `post_json` | HTTP / REST Client |

---

## 2. Authentication Architecture

Authentication is handled **strictly outside the planner** to maintain complete separation between sensitive credentials and LLM prompts:
- **Environment Variables**: Personal Access Tokens (e.g. `GITHUB_TOKEN`, `DATABASE_URL`) are read by the MCP server process at startup.
- **Trace Redaction**: All secrets and sensitive tokens are automatically masked (`***REDACTED***`) before traces are written.
- **No Hardcoded Tokens**: Zero API keys or tokens are committed to source code or git history.

---

## 3. Server Configuration

Add or modify servers in `.env` via `MCP_SERVERS`:

```json
MCP_SERVERS=[
  {"name": "github", "transport": "stdio", "command": "python", "args": ["mcp_github_server.py"]},
  {"name": "sqlite", "transport": "stdio", "command": "python", "args": ["mcp_sqlite_server.py"]},
  {"name": "fetch", "transport": "stdio", "command": "python", "args": ["mcp_fetch_server.py"]}
]
```

---

## 4. Dynamic Discovery & Zero-Keyword Planning

When the agent starts, the `ToolRegistry` dynamically connects to all enabled servers and exposes normalized tool definitions:
- Namespaces: `github.*`, `sqlite.*`, `fetch.*`
- Schema Ingestion: Parameter requirements and docstrings are provided directly to the planner.
- **Zero Keyword Rules**: The planner contains **NO hardcoded routing rules** (e.g. no `if query contains "github"`). The LLM autonomously chooses tools based purely on tool descriptions and intermediate state.

---

## 5. Human Confirmation & Safety Policies

- **Destructive Operations**: High-risk operations (such as `sqlite.delete_record` or `github.delete_issue`) automatically trigger the human confirmation policy.
- **Sandbox Isolation**: File and database operations remain strictly contained within `mcp_sandbox/`.
- **Untrusted Content Defense**: Web fetch results and issue bodies are treated as raw data; prompt injection attempts cannot hijack agent system instructions.

---

## 6. Adding a New Real MCP Application

1. **Implement or install the MCP server** (e.g., Notion, Slack, Jira, Postgres).
2. **Add the server entry** to `MCP_SERVERS` in `.env`.
3. **Run `python main.py`** — The planner immediately gains access to the new capabilities with full goal fulfillment, loop protection, and trace observability!
