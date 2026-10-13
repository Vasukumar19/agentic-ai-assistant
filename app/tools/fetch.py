"""SSRF-Hardened Web Fetch Client."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from app.core.context import ExecutionContext

# Blocked IP ranges (Private, Loopback, Link-Local, Cloud Metadata)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local / Cloud metadata (AWS, GCP, Azure)
    ipaddress.ip_network("0.0.0.0/8"),         # Current network
    ipaddress.ip_network("100.64.0.0/10"),     # Shared carrier NAT
    ipaddress.ip_network("::1/128"),           # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),         # IPv6 Link-Local
]


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP string belongs to any private or reserved network."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in BLOCKED_NETWORKS) or ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return True


def validate_url_destination(url: str) -> str:
    """
    Validate that the URL has http/https scheme and its resolved IP is not private.
    Returns canonical validated URL or raises ValueError/PermissionError.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL is missing a valid hostname.")

    # Resolve hostname to all IP addresses
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for hostname '{hostname}': {e}")

    for info in addr_info:
        ip = info[4][0]
        if is_private_ip(ip):
            raise PermissionError(
                f"SSRF Protection Blocked Request: Destination '{hostname}' resolves to private/reserved IP '{ip}'."
            )

    return url


class SafeNoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Custom redirect handler that validates target destination before following."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Validate the redirect target IP
        validate_url_destination(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SafeHttpClient:
    """Hardened HTTP fetcher protected against SSRF and resource exhaustion."""

    def __init__(self, timeout_s: float = 8.0, max_bytes: int = 50_000):
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes

    def fetch_url(self, ctx: ExecutionContext, url: str) -> str:
        """Fetch content from an external public URL safely."""
        validated_url = validate_url_destination(url)

        opener = urllib.request.build_opener(SafeNoRedirectHandler)
        req = urllib.request.Request(
            validated_url,
            headers={"User-Agent": "PersonalAssistant/2.0 (SSRF-Guarded)"},
        )

        try:
            with opener.open(req, timeout=self.timeout_s) as response:
                raw = response.read(self.max_bytes)
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return f"Network Error: {e.reason}"
        except Exception as e:
            return f"Fetch Error: {e}"


# Global default safe HTTP client
safe_http = SafeHttpClient()
