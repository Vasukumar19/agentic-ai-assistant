#!/usr/bin/env python
"""Minimal smoke test for live Google Calendar and Gmail API connectivity.

This script verifies that the saved OAuth token is valid and can reach the API.
Run it after authenticating with scripts/setup_google_oauth.py.
"""

from __future__ import annotations

import argparse
import json
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SERVICE_SCOPES = {
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
}


def build_credentials(service: str):
    token_file = os.getenv(f"{service.upper()}_TOKEN_FILE", ".google_token.json" if service == "calendar" else ".gmail_token.json")
    if not os.path.exists(token_file):
        raise FileNotFoundError(f"Token file not found: {token_file}")

    creds = Credentials.from_authorized_user_file(token_file, SERVICE_SCOPES[service])
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(f"Token for {service} is invalid or expired.")
    return creds


def main():
    parser = argparse.ArgumentParser(description="Smoke test live Google Calendar/Gmail connectivity.")
    parser.add_argument("--service", choices=["calendar", "gmail"], required=True)
    args = parser.parse_args()

    creds = build_credentials(args.service)
    api_version = "v3" if args.service == "calendar" else "v1"
    api = build(args.service, api_version, credentials=creds)

    if args.service == "calendar":
        result = api.calendarList().list().execute()
        print(json.dumps({"calendar_count": len(result.get("items", []))}, indent=2))
    else:
        result = api.users().messages().list(userId="me", maxResults=1).execute()
        print(json.dumps({"message_count": result.get("resultSizeEstimate", 0)}, indent=2))


if __name__ == "__main__":
    main()
