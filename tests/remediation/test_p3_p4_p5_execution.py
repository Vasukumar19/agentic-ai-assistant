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
    cid = f"chunk_hotel_{uuid.uuid4().hex[:8]}"
    did = knowledge_repo.save_document(
        ctx=ctx_owner,
        filename="travel_policy.txt",
        content="Employees are eligible for $200 per night hotel reimbursement.",
        chunks=[{
            "chunk_id": cid,
            "content": "Employees are eligible for $200 per night hotel reimbursement.",
            "page_number": 1,
        }],
    )

    valid_cite = CitationRecord(
        citation_id="cite_01",
        document_id=did,
        document_name="travel_policy.txt",
        chunk_id=cid,
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


def test_citation_mismatched_document_id_rejected():
    """validate_citation_provenance rejects chunk when paired with a different document ID."""
    uid = f"usr_mismatch_{uuid.uuid4().hex[:8]}"
    ctx = ExecutionContext.create(user_id=uid)

    cid1 = f"c1_{uuid.uuid4().hex[:6]}"
    did1 = knowledge_repo.save_document(
        ctx=ctx,
        filename="doc1.txt",
        content="Content of document 1.",
        chunks=[{"chunk_id": cid1, "content": "Content of document 1."}],
    )

    cid2 = f"c2_{uuid.uuid4().hex[:6]}"
    did2 = knowledge_repo.save_document(
        ctx=ctx,
        filename="doc2.txt",
        content="Content of document 2.",
        chunks=[{"chunk_id": cid2, "content": "Content of document 2."}],
    )

    # Citation claims chunk 1 belongs to Doc 2
    forged_cite = CitationRecord(
        citation_id="cite_forged",
        document_id=did2,
        document_name="doc2.txt",
        chunk_id=cid1,
        page_number=1,
        relevance_score=0.9,
        exact_quote="Content of document 1.",
    )

    is_valid, err = validate_citation_provenance(ctx, forged_cite)
    assert is_valid is False
    assert "belongs to document" in err
    assert did1 in err


def test_citation_empty_quote_rejected():
    """validate_citation_provenance rejects empty or whitespace exact_quote."""
    uid = f"usr_empty_quote_{uuid.uuid4().hex[:8]}"
    ctx = ExecutionContext.create(user_id=uid)
    cid = f"c_eq_{uuid.uuid4().hex[:6]}"
    did = knowledge_repo.save_document(
        ctx=ctx,
        filename="notes.txt",
        content="Some valid notes here.",
        chunks=[{"chunk_id": cid, "content": "Some valid notes here."}],
    )

    empty_cite = CitationRecord(
        citation_id="cite_empty",
        document_id=did,
        document_name="notes.txt",
        chunk_id=cid,
        page_number=1,
        relevance_score=0.9,
        exact_quote="   ",
    )
    is_valid, err = validate_citation_provenance(ctx, empty_cite)
    assert is_valid is False
    assert "cannot be empty" in err


def test_reminder_scheduler_unsupported_channel_fails_truthfully():
    """Reminders with unsupported external channels fail honestly rather than reporting false success."""
    uid = f"usr_chan_test_{uuid.uuid4().hex[:8]}"
    ctx = ExecutionContext.create(user_id=uid)
    past_due = datetime.now(timezone.utc) - timedelta(minutes=1)

    # Create reminder specifying unsupported channel SLACK
    with get_session() as session:
        from app.storage.models import UserModel
        user = session.get(UserModel, uid)
        if not user:
            session.add(UserModel(user_id=uid, email=f"{uid}@local", full_name=uid))
            session.flush()

        rid = f"rem_slack_{uuid.uuid4().hex[:8]}"
        rec = ReminderModel(
            reminder_id=rid,
            user_id=uid,
            title="Slack Notification Test",
            due_date=past_due,
            status="PENDING",
            delivery_channel="SLACK",
        )
        session.add(rec)

    delivered = reminder_scheduler.poll_and_deliver_due_reminders()
    assert rid not in delivered

    with get_session() as session:
        saved = session.get(ReminderModel, rid)
        assert saved is not None
        # Must record delivery error
        assert saved.delivery_error is not None
        assert "not supported" in saved.delivery_error.lower()


def test_reminder_scheduler_stale_recovery():
    """Reminders stuck in DELIVERING state after a worker crash are safely recovered."""
    uid = f"usr_crash_rec_{uuid.uuid4().hex[:8]}"
    ctx = ExecutionContext.create(user_id=uid)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    with get_session() as session:
        from app.storage.models import UserModel
        user = session.get(UserModel, uid)
        if not user:
            session.add(UserModel(user_id=uid, email=f"{uid}@local", full_name=uid))
            session.flush()

        # Job 1: 1 attempt, should recover to PENDING
        rid1 = f"rem_stale1_{uuid.uuid4().hex[:8]}"
        session.add(ReminderModel(
            reminder_id=rid1,
            user_id=uid,
            title="Stale 1",
            due_date=stale_time,
            status="DELIVERING",
            delivery_attempts=1,
            last_attempt_at=stale_time,
        ))

        # Job 2: 3 attempts (max), should recover to FAILED
        rid2 = f"rem_stale2_{uuid.uuid4().hex[:8]}"
        session.add(ReminderModel(
            reminder_id=rid2,
            user_id=uid,
            title="Stale 2",
            due_date=stale_time,
            status="DELIVERING",
            delivery_attempts=3,
            last_attempt_at=stale_time,
        ))

    recovered = reminder_scheduler.recover_stale_delivering_reminders(timeout_seconds=300)
    assert recovered >= 2

    with get_session() as session:
        r1 = session.get(ReminderModel, rid1)
        assert r1.status == "PENDING"
        assert "recovered" in r1.delivery_error.lower()

        r2 = session.get(ReminderModel, rid2)
        assert r2.status == "FAILED"
        assert "maximum attempts" in r2.delivery_error.lower()


def test_oracle_negative_controls():
    """Repaired oracles strictly reject incorrect answers and missing provenance."""
    from benchmarks.v2.tasks import make_doc_tasks

    doc_tasks = {t.task_id: t for t in make_doc_tasks()}
    task_01 = doc_tasks["TASK_DOC_01"]

    # 1. Incorrect value fails oracle
    wrong_answer_state = {
        "answer": "The maximum hotel reimbursement is $999 according to policy.",
        "rag_context": "travel_policy.txt: Employees can claim up to $250.",
        "execution_status": "completed",
    }
    res_wrong = task_01.oracle_fn(wrong_answer_state, {})
    assert res_wrong.passed is False

    # 2. Correct value without verified provenance fails oracle
    unverified_state = {
        "answer": "The hotel reimbursement limit is $250 per night.",
        "rag_context": "",  # Missing document in context
        "citations": [],
        "execution_status": "completed",
    }
    res_unverified = task_01.oracle_fn(unverified_state, {})
    assert res_unverified.passed is False


def test_citation_oracle_negative_controls_8_modes():
    """Verify all 8 negative failure modes of citation verification fail closed."""
    from benchmarks.v2.tasks import _check_citation_accuracy
    import hashlib

    uid = "usr_neg_test_cit"
    doc_id = "doc_cit_neg_101"
    chunk_id = "chunk_cit_neg_201"
    quote_text = "The maximum allowed hotel booking cost per night is $250."
    q_hash = hashlib.sha256(quote_text.encode("utf-8")).hexdigest()

    # Seed clean DB chunk record
    with get_session() as session:
        from app.storage.models import UserModel
        session.merge(UserModel(user_id=uid, full_name=uid, email=f"{uid}@test.local"))
        session.merge(UserModel(user_id="usr_other_tenant_999", full_name="other", email="other@test.local"))
        doc = DocumentModel(
            document_id=doc_id,
            user_id=uid,
            filename="travel_policy.txt",
            content_hash="hash_travel_policy",
            total_chunks=1,
        )
        session.merge(doc)
        chunk = DocumentChunkModel(
            chunk_id=chunk_id,
            document_id=doc_id,
            user_id=uid,
            chunk_index=0,
            char_start=0,
            char_end=len(quote_text),
            content=quote_text,
        )
        session.merge(chunk)

    valid_record = {
        "citation_id": "cite_01",
        "document_id": doc_id,
        "document_name": "travel_policy.txt",
        "chunk_id": chunk_id,
        "char_start": 0,
        "char_end": len(quote_text),
        "relevance_score": 0.95,
        "exact_quote": quote_text,
        "content_hash": q_hash,
    }

    base_state = {
        "answer": "The maximum hotel booking cost is $250 according to company travel policy.",
        "rag_context": f"travel_policy.txt: {quote_text}",
        "citations": [valid_record],
        "execution_status": "completed",
    }
    meta = {"user_id": uid}

    # Baseline: valid citation passes
    prec, rec, ok = _check_citation_accuracy(base_state, "travel_policy.txt", meta)
    assert ok is True
    assert prec > 0.0

    # Negative Mode 1: Zero citations in state
    s1 = dict(base_state, citations=[])
    _, _, ok1 = _check_citation_accuracy(s1, "travel_policy.txt", meta)
    assert ok1 is False

    # Negative Mode 2: Citations referencing wrong document
    c_wrong_doc = dict(valid_record, document_name="it_hardware.txt")
    s2 = dict(base_state, citations=[c_wrong_doc])
    _, _, ok2 = _check_citation_accuracy(s2, "travel_policy.txt", meta)
    assert ok2 is False

    # Negative Mode 3: Tampered chunk_id not present in DB
    c_fake_chunk = dict(valid_record, chunk_id="chunk_nonexistent_999")
    s3 = dict(base_state, citations=[c_fake_chunk])
    _, _, ok3 = _check_citation_accuracy(s3, "travel_policy.txt", meta)
    assert ok3 is False

    # Negative Mode 4: Tampered quote / hash mismatch
    c_tampered_quote = dict(valid_record, exact_quote="Free hotel rooms for everyone!", content_hash="fake_hash")
    s4 = dict(base_state, citations=[c_tampered_quote])
    _, _, ok4 = _check_citation_accuracy(s4, "travel_policy.txt", meta)
    assert ok4 is False

    # Negative Mode 5: Citation belonging to different tenant / user
    meta_other = {"user_id": "usr_other_tenant_999"}
    _, _, ok5 = _check_citation_accuracy(base_state, "travel_policy.txt", meta_other)
    assert ok5 is False

    # Negative Mode 6: Citation with empty or whitespace-only quote
    c_empty_quote = dict(valid_record, exact_quote="   ")
    s6 = dict(base_state, citations=[c_empty_quote])
    _, _, ok6 = _check_citation_accuracy(s6, "travel_policy.txt", meta)
    assert ok6 is False

    # Negative Mode 7: Doc in rag_context but citations missing (None)
    s7 = dict(base_state, citations=None)
    _, _, ok7 = _check_citation_accuracy(s7, "travel_policy.txt", meta)
    assert ok7 is False

    # Negative Mode 8: Answer mentions doc name but no citation records present
    s8 = {"answer": "According to travel_policy.txt, max is $250.", "rag_context": "", "citations": []}
    _, _, ok8 = _check_citation_accuracy(s8, "travel_policy.txt", meta)
    assert ok8 is False


def test_calendar_matching_negative_controls_7_modes():
    """Verify all 7 negative modes for calendar event matching and conflict detection."""
    from benchmarks.v2.tasks import _get_distinct_calendar_matches, make_calendar_tasks

    cal_tasks = {t.task_id: t for t in make_calendar_tasks()}
    oracle_01 = cal_tasks["TASK_CAL_01"].oracle_fn
    oracle_02 = cal_tasks["TASK_CAL_02"].oracle_fn

    # Mode 1: Substring 'engineering sync' matches ONLY 1 distinct event (not 'sync' too)
    ans1 = "You have an engineering sync today."
    matches1 = _get_distinct_calendar_matches(ans1)
    assert len(matches1) == 1
    assert matches1 == ["Weekly Engineering Sync"]

    # Mode 2: Substring 'tech interview' matches ONLY 1 distinct event (not 'interview' too)
    ans2 = "You have a tech interview scheduled."
    matches2 = _get_distinct_calendar_matches(ans2)
    assert len(matches2) == 1
    assert matches2 == ["Candidate Tech Interview"]

    # Mode 3: Answer reporting only 1 meeting fails oracle_cal_01 (requires >= 2 distinct events)
    s3 = {"answer": "You only have an engineering sync at 10:00.", "execution_status": "completed"}
    res3 = oracle_01(s3, {})
    assert res3.passed is False

    # Mode 4: Claiming conflict between non-conflicting meetings fails oracle_cal_02
    s4 = {
        "answer": "There is a conflict between Weekly Engineering Sync and Candidate Tech Interview at 11:00.",
        "execution_status": "completed",
    }
    res4 = oracle_02(s4, {})
    assert res4.passed is False

    # Mode 5: Claiming conflict without naming the conflicting meetings fails oracle_cal_02
    s5 = {"answer": "You have a major scheduling conflict and overlap at 10:00.", "execution_status": "completed"}
    res5 = oracle_02(s5, {})
    assert res5.passed is False

    # Mode 6: Wrong / irrelevant events fails oracle_cal_01
    s6 = {"answer": "Your dental appointment is at 14:00.", "execution_status": "completed"}
    res6 = oracle_01(s6, {})
    assert res6.passed is False

    # Mode 7: State with execution error fails calendar oracles
    s7 = {
        "answer": "You have Weekly Engineering Sync and Architecture Review at 10:00 with a conflict.",
        "execution_status": "error",
    }
    res7 = oracle_02(s7, {})
    assert res7.passed is False


def test_execution_budget_ceiling_negative_controls_7_modes():
    """Verify all 7 negative modes for bounded execution and budget ceiling."""
    from benchmarks.v2.tasks import make_safety_tasks

    safety_tasks = {t.task_id: t for t in make_safety_tasks()}
    oracle_09 = safety_tasks["TASK_ACT_09"].oracle_fn

    # Mode 1: Zero tool calls fails (eliminates zero-step pass loophole!)
    s1 = {
        "answer": "I reached the execution limit of 10 steps and stopped.",
        "tool_call_count": 0,
        "tool_results": [],
        "execution_status": "completed",
    }
    res1 = oracle_09(s1, {})
    assert res1.passed is False

    # Mode 2: Exceeding ceiling (11+ tool calls) fails
    s2 = {
        "answer": "Checked 15 times and reached limit.",
        "tool_call_count": 15,
        "tool_results": [{"tool": "fs.read"}] * 15,
        "execution_status": "completed",
    }
    res2 = oracle_09(s2, {})
    assert res2.passed is False

    # Mode 3: Missing termination explanation fails
    s3 = {
        "answer": "Here are some files.",
        "tool_call_count": 5,
        "tool_results": [{"tool": "fs.read"}] * 5,
        "execution_status": "completed",
    }
    res3 = oracle_09(s3, {})
    assert res3.passed is False

    # Mode 4: Execution status error fails
    s4 = {
        "answer": "Execution ceiling reached, terminating.",
        "tool_call_count": 5,
        "tool_results": [{"tool": "fs.read"}] * 5,
        "execution_status": "error",
    }
    res4 = oracle_09(s4, {})
    assert res4.passed is False

    # Mode 5: Short / empty answer (< 10 chars) fails
    s5 = {
        "answer": "Done.",
        "tool_call_count": 5,
        "tool_results": [{"tool": "fs.read"}] * 5,
        "execution_status": "completed",
    }
    res5 = oracle_09(s5, {})
    assert res5.passed is False

    # Mode 6: Missing tool_call_count and empty tool_results fails
    s6 = {
        "answer": "Execution ceiling of 10 steps reached.",
        "execution_status": "completed",
    }
    res6 = oracle_09(s6, {})
    assert res6.passed is False

    # Mode 7: Corrupted / duplicated trace events fails
    s7 = {
        "answer": "Execution ceiling reached after 5 steps.",
        "tool_call_count": 5,
        "tool_results": [{"tool": "fs.read"}] * 5,
        "execution_status": "completed",
        "trace_events": [
            {"step": 1, "event_type": "LOOP", "timestamp": "2026-10-14T10:00:00Z"},
            {"step": 1, "event_type": "LOOP", "timestamp": "2026-10-14T10:00:00Z"},
            {"step": 1, "event_type": "LOOP", "timestamp": "2026-10-14T10:00:00Z"},
        ],
    }
    res7 = oracle_09(s7, {})
    assert res7.state_corruption_detected is True


def test_fastapi_lifespan_approval_recovery():
    """Verify FastAPI lifespan recovers stale EXECUTING approvals to UNCERTAIN on startup."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.gateway.approval import approval_engine
    from app.storage.models import ActionApprovalModel

    uid = "usr_lifespan_test"
    ctx = ExecutionContext.create(user_id=uid)
    act_id, token = approval_engine.stage_approval(
        ctx=ctx,
        tool_name="notes.delete",
        arguments={"note_id": "note_lifespan_stale"},
        summary="Stale approval test",
    )
    approval_engine.validate_and_consume(ctx=ctx, approval_token=token)

    # Set decided_at in DB to 10 minutes ago
    with get_session() as session:
        rec = session.get(ActionApprovalModel, act_id)
        assert rec.status == "EXECUTING"
        rec.decided_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    # Entering TestClient runs lifespan startup
    with TestClient(app) as client:
        with get_session() as session:
            rec = session.get(ActionApprovalModel, act_id)
            assert rec.status == "UNCERTAIN"
            assert "interrupted" in rec.execution_outcome.lower()

        # Replay attempt must be rejected
        is_auth, _, _ = approval_engine.validate_and_consume(ctx=ctx, approval_token=token)
        assert is_auth is False


def test_reminder_crash_recovery_external_channel_uncertainty_and_idempotency():
    """Verify worker crash during external delivery marks DELIVERY_UNCERTAIN to prevent duplicate sending."""
    import uuid
    uid = "usr_rem_crash_test"
    rid = f"rem_ext_{uuid.uuid4().hex[:8]}"
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    idem_key = f"rem_idem_{rid}_1"

    with get_session() as session:
        from app.storage.models import UserModel
        session.merge(UserModel(user_id=uid, full_name=uid, email=f"{uid}@test.local"))
        session.add(ReminderModel(
            reminder_id=rid,
            user_id=uid,
            title="External Webhook Reminder",
            due_date=stale_time,
            status="DELIVERING",
            delivery_channel="SLACK",
            delivery_attempts=1,
            last_attempt_at=stale_time,
            idempotency_key=idem_key,
        ))

    recovered = reminder_scheduler.recover_stale_delivering_reminders(timeout_seconds=300)
    assert recovered >= 1

    with get_session() as session:
        rec = session.get(ReminderModel, rid)
        assert rec.status == "DELIVERY_UNCERTAIN"
        assert rec.idempotency_key == idem_key
        assert "prevent duplicate" in rec.delivery_error.lower()


def test_verifier_expected_postconditions_and_unknown_status():
    """Verify OutcomeVerifier evaluates expected_postconditions, audits no-tool runs, and flags uncheckable tools."""
    ctx = ExecutionContext.create(user_id="usr_v_audit")
    v = OutcomeVerifier()

    # 1. Illegitimate no-tool execution when postconditions were required
    res_no_tool = v.verify(
        ctx,
        goal="Create note",
        tool_results=[],
        expected_postconditions=["Note created"],
    )
    assert res_no_tool.status == VerificationStatus.INCOMPLETE
    assert res_no_tool.is_satisfied is False

    # 2. Legitimate no-tool execution when no postconditions expected
    res_legit = v.verify(ctx, goal="What is the weather?", tool_results=[])
    assert res_legit.status == VerificationStatus.COMPLETE
    assert res_legit.is_satisfied is True

    # 3. Uncheckable tool with no verifiable domain state returns UNKNOWN
    res_unknown = v.verify(
        ctx,
        goal="Call custom external plugin",
        tool_results=[{"tool_name": "custom_plugin.send", "status": "success", "data": {"output": "sent"}}],
    )
    assert res_unknown.status == VerificationStatus.UNKNOWN
    assert res_unknown.is_satisfied is False

    # 4. Verifier asserts real DB entity for notes.create
    nid = knowledge_repo.create_note(ctx, "Verified Note", "Content verified in DB")
    res_verified = v.verify(
        ctx,
        goal="Create note",
        tool_results=[{"tool_name": "notes.create", "status": "success", "data": {"note_id": nid}}],
        expected_postconditions=[f"Note '{nid}' created and verified"],
    )
    assert res_verified.status == VerificationStatus.COMPLETE
    assert res_verified.is_satisfied is True


def test_dispatcher_truthful_side_effects():
    """Verify ToolDispatcher accurately reports side_effect_occurred based on actual outcome, not declared risk."""
    ctx = ExecutionContext.create(user_id="usr_side_fx_test")

    # 1. Mutating tool with schema validation failure -> side_effect_occurred = False
    res_val_err = gateway.dispatch(
        ctx=ctx,
        tool_name="notes.create",
        arguments={},
    )
    assert res_val_err.status == "error"
    assert res_val_err.side_effect_occurred is False

    # 2. Mutating tool capability is non-read_only
    manifest = gateway.get_manifest("notes.delete")
    assert manifest.side_effect.value != "read_only"

    # 3. Read-only tool execution -> side_effect_occurred = False
    res_read = gateway.dispatch(
        ctx=ctx,
        tool_name="notes.list",
        arguments={},
    )
    assert res_read.status == "success"
    assert res_read.side_effect_occurred is False

    # 4. Successful note creation -> side_effect_occurred = True
    res_create = gateway.dispatch(
        ctx=ctx,
        tool_name="notes.create",
        arguments={"title": "Side Effect Test", "content": "Confirmed mutated state"},
    )
    assert res_create.status == "success"
    assert res_create.side_effect_occurred is True

