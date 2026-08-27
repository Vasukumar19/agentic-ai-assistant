# Model Context Protocol (MCP) Integration & Developer Guide

## 1. Overview

The **Agentic AI Assistant** uses the open standard **Model Context Protocol (MCP)** to interact with tools and services. 

### Core Design Principle: Zero-Keyword Planning
The planner operates entirely generically. It does **NOT** contain service-specific hardcoding such as:
```python
# FORBIDDEN ANTI-PATTERN:
if "meeting" in query:
    use_calendar()
```
Instead, when an MCP server is configured, its tools are dynamically discovered, normalized into the `ToolRegistry`, and presented to the planner via structured JSON schemas.

---

## 2. Adding a New MCP Server in 3 Steps

### Step 1: Implement the MCP Server
Create your server in Python using the official `mcp` SDK (or any language implementing MCP JSON-RPC over stdio/HTTP):

```python
# my_custom_server.py
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="database", version="1.0.0")

@mcp.tool()
async def query_users(role: str) -> str:
    """List users matching a specific role."""
    # Handle operational errors cleanly without crashing
    if not role:
        return "Error: role parameter is required."
    return '[{"id": 1, "name": "Alice", "role": "admin"}]'

if __name__ == "__main__":
    import anyio
    anyio.run(mcp.run_stdio_async)
```

### Step 2: Add to `MCP_SERVERS` Configuration
Update `.env` or `config.py` to register the server:

```json
MCP_SERVERS=[
  {"name": "database", "transport": "stdio", "command": "python", "args": ["my_custom_server.py"]}
]
```

### Step 3: Start the Agent
When the agent starts (`python main.py`), the `ToolRegistry` automatically:
1. Spawns the MCP subprocess.
2. Discovers `database.query_users`.
3. Ingests the JSON schema.
4. Makes it immediately available to the planner with full tracing and timeout protection.

---

## 3. Server Hardening Best Practices

1. **Return Clean Error Strings**: Do not allow unhandled exceptions (`KeyError`, `FileNotFoundError`) to bubble out of `@mcp.tool()`. Return `f"Error: {e}"` or structured JSON errors so the agent receives the feedback and can re-plan.
2. **Deterministic Sandboxing**: If handling file paths, restrict operations to a designated sandbox directory and reject paths containing `..` or leading slashes.
3. **Policy Hooks**: Mark destructive operations (e.g. `delete_user`, `drop_table`) so the confirmation engine automatically prompts for human authorization.
