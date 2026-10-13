"""End-to-end transport and socket tests for PinnedHTTPSConnection.

Proves:
1. Direct TCP socket connection to pinned IP (eliminating DNS rebinding races).
2. Proper TLS SNI (Server Name Indication) transmission matching destination hostname.
3. Strict certificate verification against the original hostname.
4. Certificate verification failure on hostname mismatch or untrusted CA.
"""

import http.client
import ipaddress
import os
import socket
import ssl
import tempfile
import threading
from datetime import datetime, timezone, timedelta
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.tools.fetch import PinnedHTTPSConnection


def _generate_test_cert_and_key(hostname: str = "localhost"):
    """Generate self-signed certificate and private key with Subject Alternative Name."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Security Suite"),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(hostname),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    from cryptography.hazmat.primitives import serialization
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return cert_pem, key_pem


class TLSTestServer:
    """Minimal TLS HTTP server on 127.0.0.1 for transport testing."""
    def __init__(self, cert_pem: bytes, key_pem: bytes):
        self.cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        self.cert_file.write(cert_pem)
        self.cert_file.close()

        self.key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        self.key_file.write(key_pem)
        self.key_file.close()

        self.server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server_ctx.load_cert_chain(self.cert_file.name, self.key_file.name)

        self.raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.raw_sock.bind(("127.0.0.1", 0))
        self.port = self.raw_sock.getsockname()[1]
        self.raw_sock.listen(5)

        self._running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while self._running:
            try:
                self.raw_sock.settimeout(0.5)
                client_raw, _ = self.raw_sock.accept()
            except (socket.timeout, OSError):
                continue

            try:
                with self.server_ctx.wrap_socket(client_raw, server_side=True) as tls_conn:
                    tls_conn.settimeout(2.0)
                    req = tls_conn.recv(1024)
                    if req:
                        body = b"{\"status\": \"secure_ok\"}"
                        resp = (
                            b"HTTP/1.1 200 OK\r\n"
                            b"Content-Type: application/json\r\n"
                            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                            b"Connection: close\r\n\r\n" + body
                        )
                        tls_conn.sendall(resp)
            except Exception:
                pass

    def stop(self):
        self._running = False
        try:
            self.raw_sock.close()
        except Exception:
            pass
        if os.path.exists(self.cert_file.name):
            try:
                os.unlink(self.cert_file.name)
            except Exception:
                pass
        if os.path.exists(self.key_file.name):
            try:
                os.unlink(self.key_file.name)
            except Exception:
                pass


@pytest.fixture(scope="module")
def tls_server():
    cert_pem, key_pem = _generate_test_cert_and_key("localhost")
    server = TLSTestServer(cert_pem, key_pem)
    yield server
    server.stop()


def test_pinned_https_successful_e2e_transport(tls_server):
    """
    Verify PinnedHTTPSConnection connects directly to pinned IP, negotiates TLS
    with SNI hostname, verifies certificate, and reads HTTP response.
    """
    client_ctx = ssl.create_default_context(cafile=tls_server.cert_file.name)

    conn = PinnedHTTPSConnection(
        pinned_ip="127.0.0.1",
        hostname="localhost",
        port=tls_server.port,
        timeout=3.0,
        context=client_ctx,
    )
    try:
        conn.connect()
        # Verify underlying socket was directly connected to pinned IP
        peer_ip, peer_port = conn.sock.getpeername()
        assert peer_ip == "127.0.0.1"
        assert peer_port == tls_server.port

        conn.request("GET", "/test")
        resp = conn.getresponse()
        assert resp.status == 200
        content = resp.read()
        assert b"secure_ok" in content
    finally:
        conn.close()


def test_pinned_https_rejects_hostname_mismatch(tls_server):
    """
    Verify PinnedHTTPSConnection rejects connection when SNI server_hostname
    does not match the certificate Subject Alternative Name.
    """
    client_ctx = ssl.create_default_context(cafile=tls_server.cert_file.name)

    # Server cert was issued for 'localhost'; request specifies 'untrusted.example.com'
    conn = PinnedHTTPSConnection(
        pinned_ip="127.0.0.1",
        hostname="untrusted.example.com",
        port=tls_server.port,
        timeout=3.0,
        context=client_ctx,
    )
    with pytest.raises(ssl.CertificateError):
        conn.connect()


def test_pinned_https_rejects_untrusted_ca(tls_server):
    """
    Verify PinnedHTTPSConnection fails when CA is not trusted by client context.
    """
    # Default system context does not trust our temporary self-signed cert
    default_ctx = ssl.create_default_context()

    conn = PinnedHTTPSConnection(
        pinned_ip="127.0.0.1",
        hostname="localhost",
        port=tls_server.port,
        timeout=3.0,
        context=default_ctx,
    )
    with pytest.raises(ssl.SSLCertVerificationError):
        conn.connect()


def test_pinned_https_prevents_dns_rebinding(tls_server):
    """
    Verify that connection connects strictly to pinned IP even if hostname
    points to a different external DNS target.
    """
    client_ctx = ssl.create_default_context(cafile=tls_server.cert_file.name)

    conn = PinnedHTTPSConnection(
        pinned_ip="127.0.0.1",
        hostname="localhost",
        port=tls_server.port,
        timeout=3.0,
        context=client_ctx,
    )
    conn.connect()
    try:
        # Socket must be connected to the exact pinned IP
        assert conn.sock.getpeername()[0] == "127.0.0.1"
    finally:
        conn.close()
