#!/usr/bin/env python
"""Interactive OAuth setup for Google Calendar and Gmail MCP servers.

Usage examples:
  python scripts/setup_google_oauth.py --service calendar --credentials-file client_secret.json
  python scripts/setup_google_oauth.py --service gmail --credentials-file client_secret.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


def get_scopes(service: str):
    service = service.lower()
    if service == "calendar":
        return ["https://www.googleapis.com/auth/calendar"]
    if service == "gmail":
        return [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
        ]
    raise ValueError(f"Unsupported service: {service}")


def get_token_path(service: str):
    default = ".google_token.json" if service == "calendar" else ".gmail_token.json"
    return os.getenv(f"{service.upper()}_TOKEN_FILE", default)


def load_client_config(credentials_file: str):
    path = Path(credentials_file)
    if not path.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_credentials(service: str, credentials_file: str):
    scopes = get_scopes(service)
    token_path = Path(get_token_path(service))

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # The token may belong to a deleted or rotated OAuth client.
                creds = None
        if not creds or not creds.valid:
            config = load_client_config(credentials_file)
            flow = InstalledAppFlow.from_client_config(config, scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    print(f"Google OAuth successful for {service}.")
    print(f"Token saved to: {token_path.resolve()}")
    return creds


def main():
    parser = argparse.ArgumentParser(description="Authenticate Google Calendar or Gmail for the MCP servers.")
    parser.add_argument("--service", required=True, choices=["calendar", "gmail"], help="Google service to authenticate")
    parser.add_argument("--credentials-file", required=True, help="Path to the Google OAuth client JSON file")
    args = parser.parse_args()

    creds = get_credentials(args.service, args.credentials_file)
    service_name = "calendar" if args.service == "calendar" else "gmail"
    api_version = "v3" if args.service == "calendar" else "v1"
    api = build(service_name, api_version, credentials=creds)
    print(f"Connected to Google {service_name} API successfully.")


if __name__ == "__main__":
    main()
