#!/usr/bin/env python
"""Gmail MCP server scaffold.

This follows the same pattern as the repo's other stdio MCP servers. It exposes
real Gmail operations via the Gmail API using OAuth credentials.

Required environment variables:
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
- GOOGLE_TOKEN_FILE (default: .gmail_token.json)
- GOOGLE_CREDENTIALS_FILE (optional if using OAuth JSON file)

Tools provided:
- list_messages
- get_message
- send_message
- search_messages
- delete_message
"""

from __future__ import annotations

import base64
import json
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import anyio
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="gmail", version="1.0.0")

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]
DEFAULT_TOKEN_FILE = Path(os.getenv("GMAIL_TOKEN_FILE", ".gmail_token.json"))
if not DEFAULT_TOKEN_FILE.is_absolute():
    DEFAULT_TOKEN_FILE = PROJECT_ROOT / DEFAULT_TOKEN_FILE
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")
if CREDENTIALS_FILE and not Path(CREDENTIALS_FILE).is_absolute():
    CREDENTIALS_FILE = str(PROJECT_ROOT / CREDENTIALS_FILE)
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


def _get_credentials() -> Credentials:
    """Return OAuth credentials for Gmail API."""
    creds = None
    if os.path.exists(DEFAULT_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(DEFAULT_TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_ID or not CLIENT_SECRET:
                raise RuntimeError(
                    "Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET. "
                    "Set them in the environment before using Gmail MCP tools."
                )
            if not CREDENTIALS_FILE:
                raise RuntimeError(
                    "Missing GOOGLE_CREDENTIALS_FILE. Provide the Google OAuth client JSON downloaded from Cloud Console."
                )
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as fh:
                client_config = json.load(fh)
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(DEFAULT_TOKEN_FILE, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())

    return creds


def _gmail_service():
    creds = _get_credentials()
    return build("gmail", "v1", credentials=creds)


@mcp.tool()
async def list_messages(query: str = "", max_results: int = 10) -> str:
    """List recent Gmail messages with sender, subject, date, and snippet."""
    try:
        service = _gmail_service()
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = []
        for item in results.get("messages", [])[:max_results]:
            message = service.users().messages().get(
                userId="me", id=item["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()
            headers = {
                header["name"].lower(): header.get("value", "")
                for header in message.get("payload", {}).get("headers", [])
            }
            messages.append({
                "id": message.get("id", item["id"]),
                "thread_id": message.get("threadId", item.get("threadId", "")),
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "subject": headers.get("subject", ""),
                "date": headers.get("date", ""),
                "snippet": message.get("snippet", ""),
            })
        return json.dumps({"messages": messages, "result_size_estimate": results.get("resultSizeEstimate", len(messages))}, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def search_messages(query: str = "", max_results: int = 10) -> str:
    """Search Gmail messages using Gmail query syntax."""
    try:
        service = _gmail_service()
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        return json.dumps(results, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_message(message_id: str) -> str:
    """Fetch a single email message by ID."""
    try:
        service = _gmail_service()
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        return json.dumps(msg, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def send_message(to: str, subject: str, body: str, cc: str = "") -> str:
    """Send an email using Gmail."""
    try:
        service = _gmail_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return json.dumps(sent, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def delete_message(message_id: str) -> str:
    """Delete a message from Gmail."""
    try:
        service = _gmail_service()
        service.users().messages().delete(userId="me", id=message_id).execute()
        return json.dumps({"status": "deleted", "message_id": message_id})
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    anyio.run(mcp.run_stdio_async)
