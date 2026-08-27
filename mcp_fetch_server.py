"""Web Fetch & API Model Context Protocol (MCP) Server.

Standard MCP stdio server providing external HTTP/API fetch capabilities:
- fetch.get_url
- fetch.get_json
- fetch.post_json

Includes URL validation and response size limits.
"""

import json
import urllib.request
import urllib.error
from typing import Any
import anyio
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="fetch", version="1.0.0")

MAX_FETCH_SIZE = 10000


@mcp.tool()
async def get_url(url: str) -> str:
    """Fetch text content from a web URL.

    Args:
        url: Valid HTTP/HTTPS URL
    """
    if not url:
        return "Error: url parameter is required"
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"Error: Invalid URL scheme (must be http or https): {url}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agentic-ai-mcp/1.0"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            content = resp.read(MAX_FETCH_SIZE).decode("utf-8", errors="replace")
            return content[:2000]
    except Exception as e:
        return f"Error: Failed to fetch {url}: {e}"


@mcp.tool()
async def get_json(url: str) -> str:
    """Fetch and parse JSON from a REST API endpoint.

    Args:
        url: Valid HTTP/HTTPS API URL
    """
    if not url:
        return "Error: url parameter is required"
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"Error: Invalid URL scheme: {url}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agentic-ai-mcp/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read(MAX_FETCH_SIZE).decode("utf-8", errors="replace"))
            return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return f"Error: Failed to get JSON from {url}: {e}"


@mcp.tool()
async def post_json(url: str, data: str) -> str:
    """Post JSON payload to a REST API endpoint.

    Args:
        url: Valid HTTP/HTTPS API URL
        data: JSON string payload
    """
    if not url:
        return "Error: url parameter is required"
    if not data:
        return "Error: data parameter is required"
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"Error: Invalid URL scheme: {url}"
    try:
        payload = data.encode("utf-8") if isinstance(data, str) else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"User-Agent": "agentic-ai-mcp/1.0", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            resp_body = resp.read(MAX_FETCH_SIZE).decode("utf-8", errors="replace")
            return json.dumps({"status": "posted", "response": resp_body[:500]}, ensure_ascii=False)
    except Exception as e:
        return f"Error: Failed to post to {url}: {e}"


if __name__ == "__main__":
    anyio.run(mcp.run_stdio_async)
