"""Automated Unit Tests for Stage 2: Tool Gateway, Safety & Capability Contracts."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.core.context import ExecutionContext
from app.storage.database import init_db
from app.gateway.manifest import (
    ApprovalRequirement,
    SideEffectLevel,
    ToolErrorCode,
    ToolManifest,
    ToolResultEnvelope,
)
from app.gateway.approval import ApprovalTokenEngine
from app.gateway.dispatcher import ToolDispatcher
from app.tools.filesystem import IsolatedFilesystem
from app.tools.fetch import SafeHttpClient, validate_url_destination, is_private_ip


@pytest.fixture(autouse=True)
def setup_db():
    from app.storage.database import engine, Base
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


# ==============================================================================
# 1. Approval Token Engine Tests
# ==============================================================================

def test_approval_token_staging_and_verification():
    """Verify approval token is cryptographically generated and consumed."""
    engine = ApprovalTokenEngine(secret_key="test_secret_key_123")
    ctx = ExecutionContext.create(user_id="usr_tester")

    args = {"note_id": "note_101", "purge": True}
    action_id, token = engine.stage_approval(
        ctx=ctx,
        tool_name="notes.delete",
        arguments=args,
        summary="Delete note note_101",
        risk_level=SideEffectLevel.DESTRUCTIVE,
    )

    assert action_id.startswith("act_")
    assert token.startswith("tok_")

    # Authorize with token
    is_auth, tool, auth_args = engine.validate_and_consume(
        ctx=ctx,
        approval_token=token,
        decision="APPROVE",
    )
    assert is_auth is True
    assert tool == "notes.delete"
    assert auth_args == args

    # Second consumption attempt must fail (one-time token)
    is_auth2, _, _ = engine.validate_and_consume(
        ctx=ctx,
        approval_token=token,
        decision="APPROVE",
    )
    assert is_auth2 is False


def test_approval_token_tenant_isolation():
    """Verify approval token cannot be consumed by a different tenant user."""
    engine = ApprovalTokenEngine(secret_key="test_secret_key_123")
    ctx1 = ExecutionContext.create(user_id="usr_user1")
    ctx2 = ExecutionContext.create(user_id="usr_user2")

    _, token = engine.stage_approval(
        ctx=ctx1,
        tool_name="notes.delete",
        arguments={"id": 1},
        summary="Delete note",
    )

    # User 2 tries to approve User 1's action
    is_auth, _, _ = engine.validate_and_consume(
        ctx=ctx2,
        approval_token=token,
        decision="APPROVE",
    )
    assert is_auth is False


def test_approval_token_expiration():
    """Verify expired approval token is rejected."""
    engine = ApprovalTokenEngine(secret_key="test_secret_key_123")
    ctx = ExecutionContext.create(user_id="usr_tester")

    # Expired 5 seconds ago
    _, token = engine.stage_approval(
        ctx=ctx,
        tool_name="notes.delete",
        arguments={"id": 1},
        summary="Delete note",
        expires_seconds=-5,
    )

    is_auth, _, _ = engine.validate_and_consume(
        ctx=ctx,
        approval_token=token,
        decision="APPROVE",
    )
    assert is_auth is False


# ==============================================================================
# 2. Filesystem Sandboxing Tests
# ==============================================================================

def test_isolated_filesystem_read_write(tmp_path):
    """Verify sandboxed read and write within user jail."""
    fs = IsolatedFilesystem(base_sandbox_dir=tmp_path)
    ctx = ExecutionContext.create(user_id="usr_alice")

    written = fs.write_file(ctx, "reports/summary.txt", "Sample analysis")
    assert written == len("Sample analysis")

    content = fs.read_file(ctx, "reports/summary.txt")
    assert content == "Sample analysis"

    # Verify physical path is inside usr_alice jail
    jail = fs.get_user_jail("usr_alice")
    assert (jail / "reports" / "summary.txt").exists()


def test_isolated_filesystem_path_traversal_blocked(tmp_path):
    """Verify directory traversal escapes are intercepted with PermissionError."""
    fs = IsolatedFilesystem(base_sandbox_dir=tmp_path)
    ctx = ExecutionContext.create(user_id="usr_alice")

    with pytest.raises(PermissionError):
        fs.read_file(ctx, "../../etc/passwd")

    with pytest.raises(PermissionError):
        fs.write_file(ctx, "../other_user/hack.txt", "malicious payload")


def test_isolated_filesystem_reserved_device_blocked(tmp_path):
    """Verify Windows reserved device names are blocked."""
    fs = IsolatedFilesystem(base_sandbox_dir=tmp_path)
    ctx = ExecutionContext.create(user_id="usr_alice")

    with pytest.raises(PermissionError):
        fs.write_file(ctx, "CON.txt", "freeze os")

    with pytest.raises(PermissionError):
        fs.read_file(ctx, "NUL")


# ==============================================================================
# 3. SSRF-Hardened HTTP Fetcher Tests
# ==============================================================================

def test_private_ip_detection():
    """Verify RFC 1918 and cloud metadata IP addresses are identified as private."""
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("10.0.1.5") is True
    assert is_private_ip("172.16.0.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("169.254.169.254") is True  # AWS/GCP Metadata
    assert is_private_ip("8.8.8.8") is False         # Public DNS


def test_ssrf_blocked_destination():
    """Verify private destination URLs raise PermissionError on validation."""
    with pytest.raises(PermissionError):
        validate_url_destination("http://127.0.0.1:8000/internal")

    with pytest.raises(PermissionError):
        validate_url_destination("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(ValueError):
        validate_url_destination("file:///etc/passwd")


# ==============================================================================
# 4. Tool Dispatcher & Gateway Tests
# ==============================================================================

def test_tool_dispatcher_schema_validation():
    """Verify gateway enforces schema and rejects calls with missing required arguments."""
    dispatcher = ToolDispatcher()
    ctx = ExecutionContext.create(user_id="usr_test")

    manifest = ToolManifest(
        name="notes.create",
        description="Create note",
        input_schema={"required": ["title", "content"]},
        side_effect=SideEffectLevel.REVERSIBLE_WRITE,
        approval=ApprovalRequirement.NEVER,
    )
    dispatcher.register_tool(manifest, lambda ctx, title, content: {"created": title})

    # Missing 'content'
    res = dispatcher.dispatch(ctx, "notes.create", {"title": "Title Only"})
    assert res.status == "error"
    assert res.error_code == ToolErrorCode.VALIDATION_ERROR
    assert "missing required fields" in res.error_message


def test_tool_dispatcher_approval_gating():
    """Verify destructive actions pause in awaiting_approval and execute when token provided."""
    dispatcher = ToolDispatcher()
    ctx = ExecutionContext.create(user_id="usr_test")

    executed = False

    def delete_handler(ctx, note_id):
        nonlocal executed
        executed = True
        return {"deleted": note_id}

    manifest = ToolManifest(
        name="notes.delete",
        description="Delete a note",
        input_schema={"required": ["note_id"]},
        side_effect=SideEffectLevel.DESTRUCTIVE,
        approval=ApprovalRequirement.ALWAYS,
    )
    dispatcher.register_tool(manifest, delete_handler)

    # 1. Unconfirmed attempt -> must pause in awaiting_approval
    res1 = dispatcher.dispatch(ctx, "notes.delete", {"note_id": "note_001"})
    assert res1.status == "awaiting_approval"
    assert executed is False
    token = res1.data["approval_token"]
    assert token.startswith("tok_")

    # 2. Confirmed attempt with valid token -> executes successfully
    res2 = dispatcher.dispatch(ctx, "notes.delete", {"note_id": "note_001"}, approval_token=token)
    assert res2.status == "success"
    assert executed is True
    assert res2.data["deleted"] == "note_001"
