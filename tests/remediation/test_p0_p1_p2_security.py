"""Regression tests for Priority 0, 1, and 2 remediation: Authentication, CORS, Errors, and Approvals."""

import json
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.api.server import app
from app.core.config import settings
from app.core.context import ExecutionContext
from app.gateway.approval import approval_engine
from app.knowledge.repository import knowledge_repo
from app.storage.database import init_db, get_session
from app.storage.models import NoteModel, ReminderModel, ActionApprovalModel


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# Priority 0: Authentication and Identity Security
# ==============================================================================

def test_production_mode_unauthenticated_fails_closed(client, monkeypatch):
    """In production mode, requests without valid credentials fail with 401."""
    monkeypatch.setattr(settings, "AUTH_MODE", "production")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    # Attempt chat without credentials
    res = client.post("/api/chat", json={"query": "Hello"})
    assert res.status_code == 401
    assert res.json()["error_code"] == "UNAUTHENTICATED"

    # Attempt knowledge access without credentials
    res = client.get("/api/knowledge/notes")
    assert res.status_code == 401


def test_cross_tenant_note_isolation(client):
    """User A cannot access or delete User B's notes."""
    ctx_b = ExecutionContext.create(user_id="usr_tenant_b")
    note_id = knowledge_repo.create_note(ctx_b, title="Secret B", content="Confidential info of B")

    # User A tries to delete User B's note
    res = client.delete(
        f"/api/knowledge/notes/{note_id}",
        headers={"X-Test-User-Id": "usr_tenant_a"},
    )
    # Since User A does not have access to User B's note in knowledge_repo.get_note(ctx_a), it's 404
    assert res.status_code == 404

    # Verify User B's note still exists
    assert knowledge_repo.get_note(ctx_b, note_id) is not None


def test_cross_tenant_reminder_isolation(client):
    """User A cannot complete User B's reminder."""
    ctx_b = ExecutionContext.create(user_id="usr_tenant_b")
    due_dt = datetime.now(timezone.utc) + timedelta(days=2)
    rem_id = knowledge_repo.create_reminder(ctx_b, title="B's Meeting", due_date=due_dt)

    # User A tries to complete B's reminder
    res = client.post(
        f"/api/reminders/{rem_id}/complete",
        headers={"X-Test-User-Id": "usr_tenant_a"},
    )
    assert res.status_code == 404

    # Verify B's reminder is still PENDING
    rems = knowledge_repo.list_reminders(ctx_b)
    target = next((r for r in rems if r["reminder_id"] == rem_id), None)
    assert target is not None
    assert target["status"] == "PENDING"


def test_cross_tenant_approval_denied(client):
    """User A cannot approve User B's staged action."""
    ctx_b = ExecutionContext.create(user_id="usr_tenant_b")
    act_id, token = approval_engine.stage_approval(
        ctx=ctx_b,
        tool_name="notes.delete",
        arguments={"note_id": "note_sensitive_123"},
        summary="Delete confidential note",
    )

    # User A attempts to approve B's action
    res = client.post(
        "/api/approvals/approve",
        json={"action_id": act_id, "approval_token": token, "decision": "APPROVE"},
        headers={"X-Test-User-Id": "usr_tenant_a"},
    )
    assert res.status_code == 403
    assert res.json()["error_code"] == "APPROVAL_DENIED"


# ==============================================================================
# Priority 1: CORS, Strict Validation, Safe Error Handling
# ==============================================================================

def test_production_startup_rejects_wildcard_cors(monkeypatch):
    """In production, wildcard CORS origin with credentials raises ValueError."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "APPROVAL_HMAC_SECRET", "a" * 32)
    monkeypatch.setattr(settings, "CORS_ALLOWED_ORIGINS", ["*"])

    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        settings.validate_security_configuration()


def test_validation_rejects_empty_query(client):
    """Empty query in ChatRequest is rejected with 422 Unprocessable Entity."""
    res = client.post("/api/chat", json={"query": ""}, headers={"X-Test-User-Id": "usr_test"})
    assert res.status_code == 422


def test_validation_rejects_malformed_due_date(client):
    """Malformed date in ReminderCreateRequest is rejected with 422 instead of silent now() fallback."""
    res = client.post(
        "/api/reminders",
        json={"title": "Test Reminder", "due_date": "not-a-valid-date-string"},
        headers={"X-Test-User-Id": "usr_test"},
    )
    assert res.status_code == 422


def test_safe_error_handling_hides_raw_exception(client, monkeypatch):
    """Internal server error hides exception details and provides correlation ID."""
    from app.assistant import assistant_app

    def crash_invoke(*args, **kwargs):
        raise RuntimeError("Database connection string postgres://secret_pass@10.0.0.1 failed")

    monkeypatch.setattr(assistant_app, "invoke", crash_invoke)

    res = client.post("/api/chat", json={"query": "Hello"}, headers={"X-Test-User-Id": "usr_test"})
    assert res.status_code == 500
    data = res.json()
    assert "secret_pass" not in str(data)
    assert "postgres" not in str(data)
    assert data["error_code"] == "CHAT_EXECUTION_FAILURE"


# ==============================================================================
# Priority 2: Cryptographic Approval Correctness
# ==============================================================================

def test_production_startup_rejects_weak_hmac_secret(monkeypatch):
    """Production mode refuses to start if HMAC secret is < 32 characters or default."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "APPROVAL_HMAC_SECRET", "short_secret")

    with pytest.raises(ValueError, match="APPROVAL_HMAC_SECRET must be at least 32 characters"):
        settings.get_approval_hmac_secret()


def test_tampered_argument_payload_rejected():
    """Modifying the stored arguments payload in the DB invalidates the approval token."""
    ctx = ExecutionContext.create(user_id="usr_test_crypto")
    act_id, token = approval_engine.stage_approval(
        ctx=ctx,
        tool_name="notes.delete",
        arguments={"note_id": "note_original"},
        summary="Original delete intent",
    )

    # Tamper with the database payload
    with get_session() as session:
        rec = session.query(ActionApprovalModel).filter_by(action_id=act_id).first()
        assert rec is not None
        rec.arguments_payload = json.dumps({"note_id": "note_tampered"})

    # Attempt to validate and consume
    is_auth, tool, args = approval_engine.validate_and_consume(
        ctx=ctx,
        approval_token=token,
        decision="APPROVE",
        action_id=act_id,
    )
    assert is_auth is False
    assert tool is None
    assert args is None


def test_approval_atomic_single_consumption():
    """Approval token cannot be consumed multiple times (replay prevention)."""
    ctx = ExecutionContext.create(user_id="usr_test_replay")
    act_id, token = approval_engine.stage_approval(
        ctx=ctx,
        tool_name="notes.delete",
        arguments={"note_id": "note_123"},
        summary="Delete note",
    )

    # First consumption succeeds
    is_auth_1, tool_1, args_1 = approval_engine.validate_and_consume(
        ctx=ctx,
        approval_token=token,
        decision="APPROVE",
        action_id=act_id,
    )
    assert is_auth_1 is True
    assert tool_1 == "notes.delete"
    assert args_1 == {"note_id": "note_123"}

    # Second consumption fails (token already consumed)
    is_auth_2, tool_2, args_2 = approval_engine.validate_and_consume(
        ctx=ctx,
        approval_token=token,
        decision="APPROVE",
        action_id=act_id,
    )
    assert is_auth_2 is False
    assert tool_2 is None
    assert args_2 is None
