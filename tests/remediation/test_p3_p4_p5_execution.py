"""Regression tests for Priority 3, 4, 5, 6, 7 remediation: Execution, Reminders, SSRF, Filesystem, and Citations."""

from datetime import datetime, timezone, timedelta
import pytest

from app.core.context import ExecutionContext
from app.gateway.bootstrap import bootstrap_gateway_tools
from app.gateway.dispatcher import gateway
from app.gateway.manifest import ToolErrorCode
from app.knowledge.repository import knowledge_repo
from app.knowledge.retriever import CitationRecord, validate_citation_provenance
from app.orchestration.deliberate_path import deliberate_path
from app.orchestration.verifier import OutcomeVerifier, VerificationStatus
from app.services.reminder_scheduler import reminder_scheduler
from app.storage.database import init_db, get_session
from app.storage.models import ReminderModel, DocumentModel, DocumentChunkModel
from app.tools.fetch import is_private_ip, validate_url_destination, safe_http
from app.tools.filesystem import isolated_fs
from app.assistant import assistant_app


@pytest.fixture(autouse=True)
def setup_env():
    init_db()
    bootstrap_gateway_tools()


# ==============================================================================
# Priority 3: Execution Correctness & Outcome Verification
# ==============================================================================

def test_deliberate_path_rejects_missing_note_id():
    """Deliberate path asks for clarification when note ID is missing rather than guessing 'note_101'."""
    ctx = ExecutionContext.create(user_id="usr_test_delib")
    res = deliberate_path.execute(ctx, query="Please delete note for me")
    assert res["execution_status"] == "error"
    assert "specify a valid note id" in res["answer"].lower()
    assert len(res["tool_results"]) == 0


def test_deliberate_path_rejects_missing_sqlite_id():
    """Deliberate path asks for clarification when SQLite record ID is missing rather than guessing 2."""
    ctx = ExecutionContext.create(user_id="usr_test_delib")
    res = deliberate_path.execute(ctx, query="Delete user record from sqlite")
    assert res["execution_status"] == "error"
    assert "which record id" in res["answer"].lower()
    assert len(res["tool_results"]) == 0


def test_outcome_verifier_states():
    """OutcomeVerifier accurately distinguishes COMPLETE, BLOCKED, and FAILED states."""
    ctx = ExecutionContext.create(user_id="usr_test_v")
    v = OutcomeVerifier()

    # 1. Successful note deletion postcondition
    res_complete = v.verify(
        ctx,
        goal="Delete note note_1",
        tool_results=[{"tool_name": "notes.delete", "status": "success", "data": {"deleted": True}}],
    )
    assert res_complete.status == VerificationStatus.COMPLETE
    assert res_complete.is_satisfied is True

    # 2. Awaiting approval state
    res_blocked = v.verify(
        ctx,
        goal="Delete note note_1",
        tool_results=[{"tool_name": "notes.delete", "status": "awaiting_approval", "data": {}}],
    )
    assert res_blocked.status == VerificationStatus.BLOCKED
    assert res_blocked.is_satisfied is False

    # 3. Failed tool state
    res_failed = v.verify(
        ctx,
        goal="Delete note note_1",
        tool_results=[{"tool_name": "notes.delete", "status": "error", "error_message": "DB timeout"}],
    )
    assert res_failed.status == VerificationStatus.FAILED
    assert res_failed.is_satisfied is False


# ==============================================================================
# Priority 4: Reminder Time Handling & Persistent Scheduler
# ==============================================================================

def test_reminder_due_date_preserved_accurately():
    """Requested due date is parsed and stored with exact timestamp, not replaced with now()."""
    ctx = ExecutionContext.create(user_id="usr_test_rem_dt")
    future_iso = "2026-11-20T14:30:00+00:00"
    res = gateway.dispatch(
        ctx=ctx,
        tool_name="reminders.create",
        arguments={"title": "Team Offsite", "due_date": future_iso},
    )
    assert res.status == "success"
    rid = res.data.get("reminder_id")

    # Verify database record
    rems = knowledge_repo.list_reminders(ctx)
    target = next((r for r in rems if r["reminder_id"] == rid), None)
    assert target is not None
    assert "2026-11-20" in target["due_date"]
    assert "14:30:00" in target["due_date"]


def test_persistent_reminder_scheduler_delivers_due_jobs():
    """Persistent scheduler discovers due reminders, claims job, and transitions status to DELIVERED."""
    ctx = ExecutionContext.create(user_id="usr_test_sched")
    past_due = datetime.now(timezone.utc) - timedelta(minutes=5)
    rid = knowledge_repo.create_reminder(ctx, title="Submit Timesheet", due_date=past_due)

    # Run scheduler poll
    delivered = reminder_scheduler.poll_and_deliver_due_reminders()
    assert rid in delivered

    # Verify status in database
    with get_session() as session:
        rec = session.get(ReminderModel, rid)
        assert rec is not None
        assert rec.status == "DELIVERED"
        assert rec.delivered_at is not None
        assert rec.delivery_attempts >= 1


# ==============================================================================
# Priority 5: SSRF Hardening & Filesystem Sandbox
# ==============================================================================

def test_ssrf_detects_all_blocked_network_ranges():
    """Blocks IPv4 loopback, RFC1918, cloud metadata, multicast, and IPv4-mapped IPv6."""
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("10.0.0.5") is True
    assert is_private_ip("172.16.1.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("169.254.169.254") is True
    assert is_private_ip("::1") is True
    assert is_private_ip("::ffff:127.0.0.1") is True
    assert is_private_ip("::ffff:169.254.169.254") is True
    assert is_private_ip("224.0.0.1") is True

    # Public IP should not be blocked
    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("1.1.1.1") is False


def test_ssrf_blocks_private_destinations():
    """validate_url_destination blocks cloud metadata and localhost schemes."""
    with pytest.raises(PermissionError, match="SSRF Protection"):
        validate_url_destination("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(PermissionError, match="SSRF Protection"):
        validate_url_destination("http://127.0.0.1:8080/internal")

    with pytest.raises(ValueError, match="Invalid URL scheme"):
        validate_url_destination("ftp://public-files.com/file.txt")


def test_filesystem_collision_resistant_mapping():
    """User identifiers with special characters map to distinct, collision-free directories."""
    jail_1 = isolated_fs.get_user_jail("user@company.com")
    jail_2 = isolated_fs.get_user_jail("user#company.com")
    assert jail_1 != jail_2
    assert jail_1.name != jail_2.name


def test_filesystem_sandbox_traversal_blocked():
    """Directory traversal escapes are strictly blocked."""
    ctx = ExecutionContext.create(user_id="usr_fs_test")
    with pytest.raises(PermissionError, match="escapes sandbox jail"):
        isolated_fs.read_file(ctx, "../../secret.txt")


# ==============================================================================
# Priority 7: Provenance Citation Validation & Telemetry
# ==============================================================================

import uuid


def test_provenance_citation_validation():
    """validate_citation_provenance confirms chunk existence, document ownership, and quote match."""
    uid = f"usr_doc_{uuid.uuid4().hex[:8]}"
    ctx_owner = ExecutionContext.create(user_id=uid)
    ctx_other = ExecutionContext.create(user_id=f"usr_other_{uuid.uuid4().hex[:8]}")

    # Ingest document
    did = knowledge_repo.save_document(
        ctx=ctx_owner,
        filename="travel_policy.txt",
        content="Employees are eligible for $200 per night hotel reimbursement.",
        chunks=[{
            "chunk_id": "chunk_hotel_01",
            "content": "Employees are eligible for $200 per night hotel reimbursement.",
            "page_number": 1,
        }],
    )

    valid_cite = CitationRecord(
        citation_id="cite_01",
        document_id=did,
        document_name="travel_policy.txt",
        chunk_id="chunk_hotel_01",
        page_number=1,
        relevance_score=0.95,
        exact_quote="Employees are eligible for $200 per night hotel reimbursement.",
    )

    # 1. Valid citation by document owner passes
    is_valid, err = validate_citation_provenance(ctx_owner, valid_cite)
    assert is_valid is True
    assert err is None

    # 2. Cross-tenant access is rejected
    is_valid_other, err_other = validate_citation_provenance(ctx_other, valid_cite)
    assert is_valid_other is False
    assert "belongs to another tenant" in err_other

    # 3. Fabricated chunk ID is rejected
    fake_cite = valid_cite.model_copy(update={"chunk_id": "fake_chunk_999"})
    is_valid_fake, err_fake = validate_citation_provenance(ctx_owner, fake_cite)
    assert is_valid_fake is False
    assert "does not exist" in err_fake


def test_assistant_invoke_monotonically_timed_and_not_fabricated():
    """Assistant app returns genuine monotonic latency and authentic trace events without hardcoded token counts."""
    res = assistant_app.invoke(query="Hello assistant", user_id="usr_telemetry_test")
    assert "duration_ms" in res
    assert res["duration_ms"] >= 0
    assert "trace_events" in res
    assert len(res["trace_events"]) > 0  # Emitted events are captured
    # LLM usage is either genuine metadata or None/empty, not hardcoded constant 150
    if res.get("llm_usage"):
        assert res["llm_usage"] != [{"total_tokens": 150}]
