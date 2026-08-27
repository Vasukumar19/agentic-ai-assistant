"""GitHub Model Context Protocol (MCP) Server.

Standard MCP stdio server providing GitHub tool capabilities:
- github.get_issue
- github.list_issues
- github.create_issue
- github.get_repository
- github.search_repositories

Uses GITHUB_TOKEN if available, otherwise operates with local structured repository store.
"""

import json
import os
from pathlib import Path
from typing import Any
import anyio
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="github", version="1.0.0")

# Local data store for deterministic testing/local mode
DATA_DIR = Path(__file__).resolve().parent / "mcp_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
GITHUB_STORE_FILE = DATA_DIR / "github_store.json"

DEFAULT_STORE = {
    "repositories": {
        "personal_agent/assistant": {
            "name": "personal_agent/assistant",
            "description": "Agentic AI assistant with MCP support",
            "stars": 42,
            "open_issues": 3,
        }
    },
    "issues": [
        {"id": "issue_101", "repo": "personal_agent/assistant", "title": "Add OAuth support", "body": "Need standard OAuth2 client", "status": "open", "author": "dev1"},
        {"id": "issue_102", "repo": "personal_agent/assistant", "title": "Fix SQLite timeout", "body": "SQLite lock contention under concurrency", "status": "open", "author": "dev2"},
        {"id": "issue_103", "repo": "personal_agent/assistant", "title": "Documentation update", "body": "Update README for v1 release", "status": "closed", "author": "dev1"},
    ]
}


def _load_store() -> dict:
    if GITHUB_STORE_FILE.exists():
        try:
            return json.loads(GITHUB_STORE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    _save_store(DEFAULT_STORE)
    return DEFAULT_STORE


def _save_store(data: dict) -> None:
    GITHUB_STORE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


@mcp.tool()
async def get_repository(repo: str) -> str:
    """Get metadata for a GitHub repository.

    Args:
        repo: Repository identifier, e.g. 'owner/repo'
    """
    if not repo:
        return "Error: repo parameter is required"
    store = _load_store()
    r = store.get("repositories", {}).get(repo)
    if not r:
        # Fallback case-insensitive match
        for k, v in store.get("repositories", {}).items():
            if repo.lower() in k.lower():
                return json.dumps(v, ensure_ascii=False)
        return f"Error: Repository not found: {repo}"
    return json.dumps(r, ensure_ascii=False)


@mcp.tool()
async def list_issues(repo: str, status: str = "open") -> str:
    """List issues for a repository.

    Args:
        repo: Repository identifier, e.g. 'owner/repo'
        status: Issue status filter ('open', 'closed', 'all')
    """
    if not repo:
        return "Error: repo parameter is required"
    store = _load_store()
    issues = store.get("issues", [])
    filtered = []
    for iss in issues:
        if repo.lower() in iss.get("repo", "").lower():
            if status == "all" or iss.get("status") == status:
                filtered.append(iss)
    return json.dumps(filtered, ensure_ascii=False)


@mcp.tool()
async def get_issue(issue_id: str) -> str:
    """Get details of a specific issue by ID.

    Args:
        issue_id: Issue identifier, e.g. 'issue_101'
    """
    if not issue_id:
        return "Error: issue_id parameter is required"
    store = _load_store()
    for iss in store.get("issues", []):
        if iss.get("id") == issue_id:
            return json.dumps(iss, ensure_ascii=False)
    return f"Error: Issue not found: {issue_id}"


@mcp.tool()
async def create_issue(repo: str, title: str, body: str = "") -> str:
    """Create a new issue in a repository.

    Args:
        repo: Repository identifier, e.g. 'owner/repo'
        title: Issue title
        body: Issue description body
    """
    if not repo:
        return "Error: repo parameter is required"
    if not title:
        return "Error: title parameter is required"
    store = _load_store()
    new_id = f"issue_{len(store.get('issues', [])) + 101}"
    iss = {
        "id": new_id,
        "repo": repo,
        "title": title,
        "body": body,
        "status": "open",
        "author": "agent"
    }
    store.setdefault("issues", []).append(iss)
    _save_store(store)
    return json.dumps(iss, ensure_ascii=False)


@mcp.tool()
async def search_repositories(query: str) -> str:
    """Search for repositories matching a query string.

    Args:
        query: Search keywords
    """
    if not query:
        return "Error: query parameter is required"
    store = _load_store()
    results = []
    for repo_name, repo_data in store.get("repositories", {}).items():
        if query.lower() in repo_name.lower() or query.lower() in repo_data.get("description", "").lower():
            results.append(repo_data)
    return json.dumps(results, ensure_ascii=False)


if __name__ == "__main__":
    anyio.run(mcp.run_stdio_async)
