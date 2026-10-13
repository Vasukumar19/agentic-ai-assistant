"""SSRF-Hardened Web Fetch Client with DNS Rebinding Defense & Socket IP Pinning."""

from __future__ import annotations

import http.client
import ipaddress
import logging
import socket
import ssl
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from app.core.context import ExecutionContext

logger = logging.getLogger(__name__)

# Complete list of blocked IP ranges (Private, Loopback, Link-Local, Cloud Metadata, Multicast, Broadcast)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),          # IPv4 Loopback
    ipaddress.ip_network("10.0.0.0/8"),           # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),        # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),       # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),       # Link-local / Cloud metadata (AWS, GCP, Azure, OpenStack)
    ipaddress.ip_network("0.0.0.0/8"),            # Current network / wildcard
    ipaddress.ip_network("100.64.0.0/10"),        # Shared carrier CGNAT
    ipaddress.ip_network("192.0.2.0/24"),         # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("198.51.100.0/24"),      # TEST-NET-2 (RFC 5737)
    ipaddress.ip_network("203.0.113.0/24"),       # TEST-NET-3 (RFC 5737)
    ipaddress.ip_network("198.18.0.0/15"),        # Benchmarking (RFC 2544)
    ipaddress.ip_network("224.0.0.0/4"),          # Multicast
    ipaddress.ip_network("240.0.0.0/4"),          # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"),   # Limited broadcast
    ipaddress.ip_network("::1/128"),              # IPv6 Loopback
    ipaddress.ip_network("::/128"),               # IPv6 Unspecified
    ipaddress.ip_network("fc00::/7"),             # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),            # IPv6 Link-Local
    ipaddress.ip_network("ff00::/8"),             # IPv6 Multicast
    ipaddress.ip_network("::ffff:0:0/96"),        # IPv4-mapped IPv6
    ipaddress.ip_network("2001:db8::/32"),        # Documentation IPv6
]

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}


def is_private_ip(ip_str: str) -> bool:
    """
    Check if an IP string belongs to any private, loopback, metadata, or reserved network.
    Handles standard IPv4, IPv6, and IPv4-mapped IPv6 addresses.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True

    # Check IPv4-mapped IPv6 address (e.g., ::ffff:127.0.0.1 or ::ffff:169.254.169.254)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True

    return any(ip in net for net in BLOCKED_NETWORKS)


def validate_url_destination(url: str) -> Tuple[str, str, int, str]:
    """
    Validate URL structure, scheme, port, and pre-resolve DNS against prohibited IP ranges.
    Returns (scheme, hostname, port, pinned_ip) or raises ValueError/PermissionError.
    """
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Invalid URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

    if parsed.username or parsed.password:
        raise ValueError("URL with embedded user credentials is not permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL is missing a valid hostname.")

    port = parsed.port or (443 if scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise PermissionError(f"Access denied: Port {port} is not permitted by security policy.")

    # 1. Check if hostname is directly a literal IP address
    try:
        ip_lit = ipaddress.ip_address(hostname)
        if is_private_ip(str(ip_lit)):
            raise PermissionError(
                f"SSRF Protection Blocked Request: Destination literal IP '{hostname}' is private/reserved."
            )
        return scheme, hostname, port, str(ip_lit)
    except ValueError:
        pass  # Hostname is a domain name, proceed to DNS resolution

    # 2. Resolve DNS safely and check ALL returned addresses
    try:
        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for hostname '{hostname}': {e}")

    if not addr_info:
        raise ValueError(f"No IP addresses resolved for hostname '{hostname}'.")

    pinned_ip: Optional[str] = None
    for info in addr_info:
        ip_addr = info[4][0]
        if is_private_ip(ip_addr):
            raise PermissionError(
                f"SSRF Protection Blocked Request: Hostname '{hostname}' resolves to prohibited IP '{ip_addr}'."
            )
        if not pinned_ip:
            pinned_ip = ip_addr

    return scheme, hostname, port, pinned_ip


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """
    Direct HTTPS connection to a verified pinned IP with original hostname SNI
    and strict TLS certificate validation. Eliminates DNS-rebinding races
    without broken HTTP proxy CONNECT tunneling.
    """
    def __init__(
        self,
        pinned_ip: str,
        hostname: str,
        port: int,
        timeout: float,
        context: ssl.SSLContext,
    ):
        super().__init__(pinned_ip, port=port, timeout=timeout, context=context)
        self.server_hostname = hostname

    def connect(self):
        # Directly connect TCP socket to pinned IP
        self.sock = socket.create_connection(
            (self.host, self.port), self.timeout, self.source_address
        )
        # Wrap TCP socket with TLS: SNI and cert verification matched against original hostname
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=self.server_hostname,
        )


class SafeHttpClient:
    """
    Hardened HTTP client protected against:
      - SSRF into internal networks, loopback, and cloud metadata (169.254.169.254)
      - DNS rebinding TOCTOU attacks via strict Socket IP Pinning
      - Unbounded resource exhaustion via strict size and timeout bounds
      - Unvalidated automatic redirects (redirects disabled by default)
    """

    def __init__(self, timeout_s: float = 5.0, max_bytes: int = 50_000):
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes

    def fetch_url(self, ctx: ExecutionContext, url: str) -> str:
        """
        Fetch external content safely using socket-pinned destination IP.
        """
        scheme, hostname, port, pinned_ip = validate_url_destination(url)
        path = urllib.parse.urlsplit(url).path or "/"
        query = urllib.parse.urlsplit(url).query
        req_uri = f"{path}?{query}" if query else path

        # Connect directly to pinned IP to eliminate DNS-rebinding race
        conn: Optional[http.client.HTTPConnection] = None
        try:
            if scheme == "https":
                # Create SSL context verifying cert against original hostname (SNI)
                ssl_ctx = ssl.create_default_context()
                conn = PinnedHTTPSConnection(
                    pinned_ip,
                    hostname=hostname,
                    port=port,
                    timeout=self.timeout_s,
                    context=ssl_ctx,
                )
            else:
                conn = http.client.HTTPConnection(
                    pinned_ip,
                    port=port,
                    timeout=self.timeout_s,
                )

            headers = {
                "Host": hostname,
                "User-Agent": "PersonalAssistant/2.0 (SSRF-Guarded)",
                "Accept": "text/html,application/xhtml+xml,application/json,text/plain",
                "Connection": "close",
            }

            conn.request("GET", req_uri, headers=headers)
            resp = conn.getresponse()

            # Handle redirects: disable automatic follow by default
            if resp.status in (301, 302, 303, 307, 308):
                redirect_loc = resp.getheader("Location", "")
                raise PermissionError(
                    f"Automatic redirect to '{redirect_loc}' blocked by security policy."
                )

            if resp.status >= 400:
                raise ValueError(f"HTTP Error {resp.status}: {resp.reason}")

            raw = resp.read(self.max_bytes)
            return raw.decode("utf-8", errors="replace")

        except PermissionError:
            raise
        except ValueError:
            raise
        except socket.timeout:
            raise TimeoutError(f"HTTP connection timed out after {self.timeout_s}s.")
        except Exception as e:
            logger.warning("SafeHttpClient network error for %s (%s): %s", hostname, pinned_ip, e)
            raise ValueError(f"Network transport error: {type(e).__name__}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


# Global default safe HTTP client
safe_http = SafeHttpClient()
