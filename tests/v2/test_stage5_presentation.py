"""Unit & Integration Tests for Stage 5: Presentation Layer (CLI & FastAPI)."""

import pytest
from fastapi.testclient import TestClient

from app.api.server import app
from app.cli import run_one_shot
from app.core.context import ExecutionContext
from app.knowledge.repository import knowledge_repo


@pytest.fixture
def client():
    from app.storage.database import init_db
    init_db()
    return TestClient(app)


def test_healthz_and_settings(client):
    """Verify healthcheck and system settings endpoints."""
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"

    res_set = client.get("/api/settings")
    assert res_set.status_code == 200
    data = res_set.json()
    assert data["architecture"] == "v2_modular_monolith"
    assert data["database"] == "sqlite_wal"


def test_api_chat_fast_path(client):
    """Verify /api/chat handles fast-path chat greeting cleanly."""
    res = client.post(
        "/api/chat",
        json={"query": "Hello there", "user_id": "usr_test_api"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "Assistant" in data["answer"] or "Hello" in data["answer"]
    assert data["execution_status"] == "completed"
    assert data["route"] == "FAST_CHAT"
    assert data["user_id"] == "usr_test_api"


def test_api_knowledge_facts_lifecycle(client):
    """Verify /api/knowledge/facts can store and retrieve facts."""
    user_id = "usr_facts_test"
    # 1. Post fact
    res = client.post(
        f"/api/knowledge/facts?user_id={user_id}",
        json={"key": "favorite_editor", "value": "Neovim"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "saved"

    # 2. Get facts
    res_get = client.get(f"/api/knowledge/facts?user_id={user_id}")
    assert res_get.status_code == 200
    facts = res_get.json()["facts"]
    assert facts.get("favorite_editor") == "Neovim"


def test_api_knowledge_notes_lifecycle(client):
    """Verify /api/knowledge/notes can create and list notes."""
    user_id = "usr_notes_test"
    # 1. Create note
    res = client.post(
        f"/api/knowledge/notes?user_id={user_id}",
        json={"title": "Sprint Goals", "content": "Complete V2 cutover benchmarks."},
    )
    assert res.status_code == 200
    nid = res.json()["note_id"]
    assert nid.startswith("note_")

    # 2. List notes
    res_list = client.get(f"/api/knowledge/notes?user_id={user_id}")
    assert res_list.status_code == 200
    notes = res_list.json()["notes"]
    assert any(n["note_id"] == nid for n in notes)


def test_api_reminders_lifecycle(client):
    """Verify /api/reminders creation, listing, and completion."""
    user_id = "usr_rem_test"
    # 1. Create reminder
    res = client.post(
        f"/api/reminders?user_id={user_id}",
        json={"title": "Submit conference paper", "due_date": "2026-11-01T12:00:00"},
    )
    assert res.status_code == 200
    rid = res.json()["reminder_id"]
    assert rid.startswith("rem_")

    # 2. List reminders
    res_list = client.get(f"/api/reminders?user_id={user_id}")
    assert res_list.status_code == 200
    rems = res_list.json()["reminders"]
    assert any(r["reminder_id"] == rid for r in rems)

    # 3. Complete reminder
    res_comp = client.post(f"/api/reminders/{rid}/complete?user_id={user_id}")
    assert res_comp.status_code == 200
    assert res_comp.json()["status"] == "completed"


def test_api_chat_approval_gating(client):
    """Verify /api/chat pauses on destructive delete and provides approval token."""
    user_id = "usr_del_test"
    ctx = ExecutionContext.create(user_id=user_id)
    nid = knowledge_repo.create_note(ctx, title="To Delete", content="Temporary")

    res = client.post(
        "/api/chat",
        json={"query": f"Delete note {nid}", "user_id": user_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["execution_status"] == "awaiting_approval"
    assert data["pending_approval"] is not None
    token = data["pending_approval"]["approval_token"]
    assert token.startswith("tok_")

    # Resume with token via /api/approvals/approve
    res_app = client.post(
        "/api/approvals/approve",
        json={"approval_token": token, "user_id": user_id},
    )
    assert res_app.status_code == 200
    app_data = res_app.json()
    assert app_data["execution_status"] == "completed"
    assert "deleted" in app_data["answer"].lower()


def test_cli_one_shot_execution(capsys):
    """Verify CLI one-shot execution runs and prints output."""
    run_one_shot(query="Hello from CLI", user_id="usr_cli_test")
    captured = capsys.readouterr()
    assert len(captured.out) > 0
    assert "Assistant" in captured.out or "Hello" in captured.out
