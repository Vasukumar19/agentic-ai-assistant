"""Automated Unit Tests for Stage 3: Knowledge Repository & Unified Retrieval Pipeline."""

import pytest
from datetime import datetime, timezone, timedelta

from app.core.context import ExecutionContext
from app.storage.database import init_db, engine, Base
from app.knowledge.repository import knowledge_repo
from app.knowledge.retriever import knowledge_retriever, CitationRecord
from app.knowledge.context_builder import context_builder
from scripts.migrate_v1_data import migrate_all_v1_data


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


# ==============================================================================
# 1. Knowledge Repository CRUD Tests
# ==============================================================================

def test_profile_fact_storage_and_overwrite():
    """Verify profile facts are stored, updated, and queried per tenant."""
    ctx = ExecutionContext.create(user_id="usr_profile_tester")

    knowledge_repo.set_profile_fact(ctx, key="role", value="AI Engineer")
    facts1 = knowledge_repo.get_profile_facts(ctx)
    assert facts1.get("role") == "AI Engineer"

    # Overwrite fact
    knowledge_repo.set_profile_fact(ctx, key="role", value="Principal Architect")
    facts2 = knowledge_repo.get_profile_facts(ctx)
    assert facts2.get("role") == "Principal Architect"

    # Delete fact
    deleted = knowledge_repo.delete_profile_fact(ctx, key="role")
    assert deleted is True
    assert "role" not in knowledge_repo.get_profile_facts(ctx)


def test_note_lifecycle():
    """Verify note creation, retrieval, and soft delete."""
    ctx = ExecutionContext.create(user_id="usr_note_tester")

    nid = knowledge_repo.create_note(ctx, title="Sprint Goals", content="Ship Stage 3")
    assert nid.startswith("note_")

    note = knowledge_repo.get_note(ctx, nid)
    assert note is not None
    assert note["title"] == "Sprint Goals"
    assert note["content"] == "Ship Stage 3"

    # Soft delete note
    knowledge_repo.delete_note(ctx, nid, soft_delete=True)
    assert knowledge_repo.get_note(ctx, nid) is None

    # Verify note is still in db with is_deleted=True
    all_notes = knowledge_repo.list_notes(ctx, include_deleted=True)
    assert any(n["note_id"] == nid and n["is_deleted"] is True for n in all_notes)


def test_reminder_lifecycle():
    """Verify reminder creation, listing, and completion."""
    ctx = ExecutionContext.create(user_id="usr_rem_tester")
    due = datetime.now(timezone.utc) + timedelta(days=2)

    rid = knowledge_repo.create_reminder(ctx, title="Submit budget", due_date=due)
    assert rid.startswith("rem_")

    rems = knowledge_repo.list_reminders(ctx, status="PENDING")
    assert len(rems) == 1
    assert rems[0]["reminder_id"] == rid

    knowledge_repo.complete_reminder(ctx, rid)
    pending = knowledge_repo.list_reminders(ctx, status="PENDING")
    assert len(pending) == 0


def test_document_and_chunk_storage():
    """Verify document chunks are stored and queried with metadata."""
    ctx = ExecutionContext.create(user_id="usr_doc_tester")

    chunks = [
        {"chunk_id": "chunk_01", "page_number": 1, "char_start": 0, "char_end": 45, "content": "Flight reimbursement policy: economy class."},
        {"chunk_id": "chunk_02", "page_number": 1, "char_start": 46, "char_end": 90, "content": "Hotel booking cap: $250 per night."},
    ]
    doc_id = knowledge_repo.save_document(
        ctx=ctx,
        filename="travel.txt",
        content="Flight reimbursement policy: economy class. Hotel booking cap: $250 per night.",
        chunks=chunks,
    )

    all_chunks = knowledge_repo.get_all_chunks(ctx)
    assert len(all_chunks) == 2
    assert all_chunks[0]["filename"] == "travel.txt"
    assert all_chunks[1]["chunk_id"] == "chunk_02"


# ==============================================================================
# 2. Hybrid Retrieval with Provenance Tests
# ==============================================================================

def test_hybrid_retrieval_citation_provenance():
    """Verify retriever returns CitationRecord objects with exact chunk provenance."""
    ctx = ExecutionContext.create(user_id="usr_retrieval_tester")

    chunks = [
        {"chunk_id": "chunk_hotel", "page_number": 1, "content": "Hotel bookings are strictly capped at $250 per night."},
        {"chunk_id": "chunk_hardware", "page_number": 1, "content": "Engineers receive a MacBook Pro 16-inch M3 Max."},
    ]
    knowledge_repo.save_document(
        ctx=ctx,
        filename="travel_policy.txt",
        content="Hotel bookings are strictly capped at $250 per night.",
        chunks=[chunks[0]],
    )
    knowledge_repo.save_document(
        ctx=ctx,
        filename="it_hardware.txt",
        content="Engineers receive a MacBook Pro 16-inch M3 Max.",
        chunks=[chunks[1]],
    )

    citations = knowledge_retriever.retrieve(ctx, query="hotel booking reimbursement cap")
    assert len(citations) >= 1
    top_cite = citations[0]

    assert isinstance(top_cite, CitationRecord)
    assert top_cite.citation_id == "cite_01"
    assert top_cite.document_name == "travel_policy.txt"
    assert top_cite.chunk_id == "chunk_hotel"
    assert "$250" in top_cite.exact_quote


# ==============================================================================
# 3. Bounded Context Builder Tests
# ==============================================================================

def test_bounded_context_builder():
    """Verify context builder outputs prompt with explicit citation blocks and bounds tokens."""
    ctx = ExecutionContext.create(user_id="usr_context_tester")

    facts = {"primary_language": "Python", "role": "Architect"}
    calendar = [{"time": "10:00", "title": "Architecture Review", "status": "confirmed"}]
    citations = [
        CitationRecord(
            citation_id="cite_01",
            document_id="doc_travel",
            document_name="travel_policy.txt",
            chunk_id="c01",
            relevance_score=0.95,
            exact_quote="Hotel limit is $250.",
        )
    ]

    context_str, token_est = context_builder.build_context(
        ctx=ctx,
        profile_facts=facts,
        calendar_events=calendar,
        citations=citations,
    )

    assert "=== CURRENT DATE & TIME ===" in context_str
    assert "=== USER PROFILE & FACTS ===" in context_str
    assert "Primary Language: Python" in context_str
    assert "=== TODAY'S CALENDAR COMMITMENTS ===" in context_str
    assert "Architecture Review" in context_str
    assert "=== VERIFIED SOURCE PASSAGES ===" in context_str
    assert "[cite_01 | travel_policy.txt p.1]" in context_str
    assert token_est < 1000


# ==============================================================================
# 4. End-to-End Migration Script Test
# ==============================================================================

def test_v1_migration_script():
    """Verify data migration script loads existing repo files into database without error."""
    migrate_all_v1_data(target_user_id="usr_migrated")
    ctx = ExecutionContext.create(user_id="usr_migrated")

    # Verify facts were imported
    facts = knowledge_repo.get_profile_facts(ctx)
    assert len(facts) >= 1

    # Verify documents were imported
    chunks = knowledge_repo.get_all_chunks(ctx)
    assert len(chunks) >= 10
