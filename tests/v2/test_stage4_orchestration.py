"""Automated Unit Tests for Stage 4: Dual-Path Orchestrator & Execution Engine."""

import pytest
from app.core.context import ExecutionContext
from app.storage.database import init_db, engine, Base
from app.gateway.bootstrap import bootstrap_gateway_tools
from app.knowledge.repository import knowledge_repo
from app.orchestration.router import router, IntentRoute
from app.orchestration.fast_path import fast_path
from app.orchestration.deliberate_path import deliberate_path
from app.assistant import assistant_app


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    bootstrap_gateway_tools()
    yield
    Base.metadata.drop_all(bind=engine)


# ==============================================================================
# 1. Intent Router Tests
# ==============================================================================

def test_intent_router_classification():
    """Verify router cleanly categorizes queries across fast and deliberate paths."""
    ctx = ExecutionContext.create(user_id="usr_router_test")

    # Greetings
    c1 = router.classify(ctx, "hello there!")
    assert c1.route == IntentRoute.FAST_CHAT

    # Memory update
    c2 = router.classify(ctx, "Remember that I prefer working in Python")
    assert c2.route == IntentRoute.MEMORY_MUTATION

    # Document Q&A
    c3 = router.classify(ctx, "What is the corporate hotel cap per night?")
    assert c3.route == IntentRoute.FAST_INFO

    # Destructive action
    c4 = router.classify(ctx, "Delete note note_101 immediately")
    assert c4.route == IntentRoute.DELIBERATE
    assert c4.requires_approval is True


# ==============================================================================
# 2. Fast Path Execution Tests
# ==============================================================================

def test_fast_path_chat():
    """Verify chat route returns friendly small talk response."""
    ctx = ExecutionContext.create(user_id="usr_fast_test")
    res = fast_path.execute(ctx, query="hi", route=IntentRoute.FAST_CHAT)
    assert "Assistant" in res["answer"]
    assert res["execution_status"] == "completed"


def test_fast_path_memory_mutation():
    """Verify memory route extracts and stores facts in repository."""
    ctx = ExecutionContext.create(user_id="usr_mem_test")
    res = fast_path.execute(
        ctx,
        query="My job title is Staff Research Engineer",
        route=IntentRoute.MEMORY_MUTATION,
    )
    assert res["execution_status"] == "completed"
    assert "Staff Research Engineer" in res["answer"]

    # Verify fact is stored
    facts = knowledge_repo.get_profile_facts(ctx)
    assert facts.get("role") == "Staff Research Engineer"


# ==============================================================================
# 3. Deliberate Path Execution & Approval Resumption Tests
# ==============================================================================

def test_deliberate_path_approval_flow():
    """Verify deliberate path pauses on destructive action and resumes with token."""
    ctx = ExecutionContext.create(user_id="usr_delib_test")
    knowledge_repo.create_note(ctx, title="Sensitive Note", content="Secret", note_id="note_sensitive")

    # 1. Initial attempt -> must halt in awaiting_approval
    res1 = deliberate_path.execute(ctx, query="Delete note note_sensitive")
    assert res1["execution_status"] == "awaiting_approval"
    token = res1["pending_approval"]["approval_token"]
    assert token.startswith("tok_")

    # Note must still exist
    assert knowledge_repo.get_note(ctx, "note_sensitive") is not None

    # 2. Resume with token -> executes deletion
    res2 = deliberate_path.execute(ctx, query="Delete note note_sensitive", approval_token=token)
    assert res2["execution_status"] == "completed"
    assert "successfully deleted" in res2["answer"]

    # Note must now be soft-deleted
    assert knowledge_repo.get_note(ctx, "note_sensitive") is None


# ==============================================================================
# 4. Assistant App End-to-End Tests
# ==============================================================================

def test_assistant_app_invoke():
    """Verify AssistantApp coordinates identity, routing, and response payload."""
    res = assistant_app.invoke(
        query="Hello! How are you?",
        user_id="usr_alex",
    )
    assert res["execution_status"] == "completed"
    assert res["user_id"] == "usr_alex"
    assert res["correlation_id"].startswith("cor_")
    assert res["route"] == IntentRoute.FAST_CHAT
