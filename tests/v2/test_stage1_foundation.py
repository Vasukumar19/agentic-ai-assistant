"""Automated Unit Tests for Stage 1: Foundation & Data Infrastructure."""

import os
import json
import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.core.context import ExecutionContext
from app.core.config import Settings
from app.storage.database import engine, Base, init_db, get_session
from app.storage.models import (
    UserModel,
    ConversationModel,
    MessageModel,
    NoteModel,
    ReminderModel,
    ProfileFactModel,
    ActionApprovalModel,
)
from app.observability.events import SystemTraceEvent, EventSeverity
from app.observability.sink import InMemorySink, JsonlFileSink, emit_event


# ==============================================================================
# 1. ExecutionContext Tests
# ==============================================================================

def test_execution_context_creation():
    """Verify ExecutionContext creates typed unique identities."""
    ctx = ExecutionContext.create(user_id="usr_alex")
    assert ctx.user_id == "usr_alex"
    assert ctx.session_id.startswith("ses_")
    assert ctx.execution_id.startswith("exec_")
    assert ctx.correlation_id.startswith("cor_")
    assert ctx.created_at is not None


def test_execution_context_immutability():
    """Verify ExecutionContext is strictly immutable."""
    ctx = ExecutionContext.create(user_id="usr_alex")
    with pytest.raises(FrozenInstanceError):
        ctx.user_id = "usr_hacker"  # type: ignore


def test_execution_context_step_derivation():
    """Verify with_step derives a new context preserving correlation and tenant IDs."""
    ctx = ExecutionContext.create(user_id="usr_alex", session_id="ses_123")
    step_ctx = ctx.with_step(step_id="step_01", plan_id="plan_abc")

    assert step_ctx.user_id == "usr_alex"
    assert step_ctx.session_id == "ses_123"
    assert step_ctx.correlation_id == ctx.correlation_id
    assert step_ctx.step_id == "step_01"
    assert step_ctx.plan_id == "plan_abc"
    # Ensure original is unchanged
    assert ctx.step_id is None


def test_execution_context_serialization():
    """Verify ExecutionContext cleanly converts to dictionary."""
    ctx = ExecutionContext.create(user_id="usr_alex")
    d = ctx.to_dict()
    assert isinstance(d, dict)
    assert d["user_id"] == "usr_alex"
    assert "correlation_id" in d


# ==============================================================================
# 2. Settings Tests
# ==============================================================================

def test_settings_initialization(tmp_path):
    """Verify Settings initializes with valid paths and sane defaults."""
    s = Settings(STORAGE_DIR=tmp_path / "storage")
    s.ensure_directories()
    assert (tmp_path / "storage").exists()
    assert s.CONTEXT_TOKEN_BUDGET == 3500
    assert s.MAX_EXECUTION_STEPS == 10


# ==============================================================================
# 3. Storage & Relational Database Tests
# ==============================================================================

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Ensure clean schema for each test."""
    init_db()
    yield
    # Clean tables
    Base.metadata.drop_all(bind=engine)


def test_database_schema_initialization():
    """Verify all V2 tables are created on database engine."""
    init_db()
    table_names = list(Base.metadata.tables.keys())
    expected = [
        "users",
        "conversations",
        "messages",
        "documents",
        "document_chunks",
        "profile_facts",
        "semantic_memories",
        "notes",
        "reminders",
        "executions",
        "execution_steps",
        "action_approvals",
    ]
    for exp in expected:
        assert exp in table_names, f"Table {exp} missing from schema metadata"


def test_user_and_note_persistence():
    """Verify inserting and querying users and notes with cascade behavior."""
    init_db()
    with get_session() as session:
        user = UserModel(
            user_id="usr_alex",
            email="alex@vertex.ai",
            full_name="Dr. Alex Vance",
            timezone="Europe/Zurich",
        )
        session.add(user)

        note = NoteModel(
            note_id="note_001",
            user_id="usr_alex",
            title="Migration Strategy",
            content="Stage 1 foundation established.",
        )
        session.add(note)

    # Query back in separate session
    with get_session() as session:
        queried_user = session.get(UserModel, "usr_alex")
        assert queried_user is not None
        assert queried_user.full_name == "Dr. Alex Vance"
        assert len(queried_user.notes) == 1
        assert queried_user.notes[0].title == "Migration Strategy"


def test_cascade_delete_user():
    """Verify deleting a user cascades to their notes and conversations."""
    init_db()
    with get_session() as session:
        user = UserModel(
            user_id="usr_delete_test",
            email="delete@example.com",
            full_name="Temporary User",
        )
        session.add(user)
        note = NoteModel(
            note_id="note_temp",
            user_id="usr_delete_test",
            title="Temp Note",
            content="Will be deleted",
        )
        session.add(note)

    with get_session() as session:
        u = session.get(UserModel, "usr_delete_test")
        session.delete(u)

    with get_session() as session:
        assert session.get(UserModel, "usr_delete_test") is None
        assert session.get(NoteModel, "note_temp") is None


def test_action_approval_token_persistence():
    """Verify action approval tokens persist and query cleanly."""
    init_db()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    with get_session() as session:
        user = UserModel(user_id="usr_approver", email="approver@test.com", full_name="Approver")
        conv = ConversationModel(session_id="ses_appr", user_id="usr_approver")
        session.add_all([user, conv])

        from app.storage.models import ExecutionModel
        exec_model = ExecutionModel(execution_id="exec_appr", session_id="ses_appr", user_id="usr_approver", query="Delete Note")
        session.add(exec_model)

        approval = ActionApprovalModel(
            action_id="act_001",
            execution_id="exec_appr",
            user_id="usr_approver",
            tool_name="notes.delete",
            arguments_payload=json.dumps({"note_id": "note_101"}),
            arguments_hash="hash_abc123",
            approval_token="tok_hmac_valid_9981",
            summary="Delete note note_101",
            status="PENDING",
            expires_at=expires,
        )
        session.add(approval)

    with get_session() as session:
        appr = session.query(ActionApprovalModel).filter_by(approval_token="tok_hmac_valid_9981").first()
        assert appr is not None
        assert appr.tool_name == "notes.delete"
        assert appr.status == "PENDING"


# ==============================================================================
# 4. Decoupled Observability Sink Tests
# ==============================================================================

def test_in_memory_sink():
    """Verify InMemorySink captures events without mutating graph state."""
    sink = InMemorySink()
    ctx = ExecutionContext.create(user_id="usr_test")

    ev = emit_event(
        ctx=ctx,
        component="test_component",
        event_type="TEST_EVENT",
        payload={"key": "value"},
        duration_ms=42,
        sink=sink,
    )

    events = sink.get_events()
    assert len(events) == 1
    assert events[0].event_id == ev.event_id
    assert events[0].correlation_id == ctx.correlation_id
    assert events[0].duration_ms == 42
    assert events[0].payload == {"key": "value"}


def test_jsonl_file_sink(tmp_path):
    """Verify JsonlFileSink writes valid JSON lines to disk."""
    sink = JsonlFileSink(trace_dir=tmp_path)
    ctx = ExecutionContext.create(user_id="usr_test")

    emit_event(
        ctx=ctx,
        component="gateway",
        event_type="TOOL_EXECUTED",
        payload={"tool": "notes.list"},
        sink=sink,
    )

    files = list(tmp_path.glob("trace_*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8").strip()
    data = json.loads(content)

    assert data["component"] == "gateway"
    assert data["event_type"] == "TOOL_EXECUTED"
    assert data["correlation_id"] == ctx.correlation_id
    assert data["user_id"] == "usr_test"
