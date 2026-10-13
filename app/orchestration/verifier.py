"""Semantic & Postcondition-Based Outcome Verifier."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from app.core.context import ExecutionContext


class VerificationStatus(str, Enum):
    """Explicit verification outcome states."""
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class PostconditionType(str, Enum):
    """Supported deterministic domain entity postcondition types."""
    NOTE_STATE = "NOTE_STATE"
    REMINDER_STATE = "REMINDER_STATE"
    DOCUMENT_STATE = "DOCUMENT_STATE"
    FILE_STATE = "FILE_STATE"
    CUSTOM = "CUSTOM"
    UNSPECIFIED = "UNSPECIFIED"


class TypedPostcondition(BaseModel):
    """
    Authoritative, typed domain postcondition requirement evaluated directly
    against persistent database or system state.
    """
    condition_type: PostconditionType
    entity_id: Optional[str] = None
    expected_state: str  # e.g. "deleted", "exists", "completed", "pending"
    target_path: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None

    def evaluate(self, ctx: ExecutionContext) -> Tuple[bool, str]:
        """
        Evaluate the postcondition directly against authoritative state in the database/filesystem.
        Returns (is_satisfied: bool, message: str).
        """
        from app.storage.database import get_session
        from app.storage.models import NoteModel, ReminderModel, DocumentModel

        if self.condition_type == PostconditionType.NOTE_STATE:
            nid = self.entity_id or self.details.get("note_id")
            if not nid:
                return False, "Note postcondition missing note_id."
            with get_session() as session:
                note = session.query(NoteModel).filter_by(user_id=ctx.user_id, note_id=nid).first()
                exp_st = self.expected_state.lower()
                if exp_st in ("deleted", "removed"):
                    if note is None or note.is_deleted:
                        return True, f"Note '{nid}' confirmed deleted in repository."
                    return False, f"Note '{nid}' still present/active in repository (expected deleted)."
                elif exp_st in ("exists", "active", "created", "persisted"):
                    if note and not note.is_deleted:
                        return True, f"Note '{nid}' created and verified in repository."
                    return False, f"Note '{nid}' not found or marked deleted in repository."
                else:
                    return False, f"Unknown expected state '{self.expected_state}' for note."

        elif self.condition_type == PostconditionType.REMINDER_STATE:
            rid = self.entity_id or self.details.get("reminder_id")
            if not rid:
                return False, "Reminder postcondition missing reminder_id."
            with get_session() as session:
                rem = session.query(ReminderModel).filter_by(user_id=ctx.user_id, reminder_id=rid).first()
                exp_st = self.expected_state.lower()
                if exp_st in ("completed", "done"):
                    if rem and rem.status == "COMPLETED":
                        return True, f"Reminder '{rid}' confirmed COMPLETED in repository."
                    status_desc = rem.status if rem else "not found"
                    return False, f"Reminder '{rid}' status is '{status_desc}' (expected COMPLETED)."
                elif exp_st in ("pending", "scheduled", "active"):
                    if rem and rem.status in ("PENDING", "ACTIVE"):
                        return True, f"Reminder '{rid}' scheduled and verified in repository."
                    status_desc = rem.status if rem else "not found"
                    return False, f"Reminder '{rid}' status is '{status_desc}' (expected PENDING/ACTIVE)."
                elif exp_st in ("deleted", "cancelled"):
                    if rem is None or rem.status == "CANCELLED":
                        return True, f"Reminder '{rid}' confirmed deleted/cancelled in repository."
                    return False, f"Reminder '{rid}' still present with status '{rem.status}'."
                else:
                    return False, f"Unknown expected state '{self.expected_state}' for reminder."

        elif self.condition_type == PostconditionType.DOCUMENT_STATE:
            did = self.entity_id or self.details.get("document_id")
            fname = self.details.get("filename")
            with get_session() as session:
                query = session.query(DocumentModel).filter_by(user_id=ctx.user_id)
                if did:
                    query = query.filter_by(document_id=did)
                elif fname:
                    query = query.filter_by(filename=fname)
                else:
                    return False, "Document postcondition missing document_id or filename."
                doc = query.first()
                exp_st = self.expected_state.lower()
                if exp_st in ("persisted", "exists"):
                    if doc:
                        return True, f"Document '{doc.document_id}' verified in repository."
                    return False, f"Document '{did or fname}' not found in repository."
                elif exp_st in ("deleted", "removed"):
                    if not doc:
                        return True, "Document confirmed absent from repository."
                    return False, f"Document '{doc.document_id}' still present in repository."
                return False, f"Unknown expected state '{self.expected_state}' for document."

        elif self.condition_type == PostconditionType.FILE_STATE:
            from app.gateway.isolated_fs import isolated_fs
            path = self.target_path or self.entity_id or self.details.get("path")
            if not path:
                return False, "File postcondition missing target path."
            exists = isolated_fs.exists(ctx, path)
            exp_st = self.expected_state.lower()
            if exp_st in ("exists", "created", "persisted"):
                if exists:
                    return True, f"File '{path}' verified in isolated filesystem."
                return False, f"File '{path}' not found in isolated filesystem."
            elif exp_st in ("deleted", "removed"):
                if not exists:
                    return True, f"File '{path}' confirmed absent in isolated filesystem."
                return False, f"File '{path}' still exists in isolated filesystem."
            return False, f"Unknown expected state '{self.expected_state}' for file."

        elif self.condition_type == PostconditionType.CUSTOM:
            eval_fn = self.details.get("eval_fn")
            if callable(eval_fn):
                return eval_fn(ctx)
            return False, f"Custom postcondition '{self.description}' missing callable evaluation function."

        elif self.condition_type == PostconditionType.UNSPECIFIED:
            return False, f"Postcondition '{self.description}' lacks deterministic entity identity or schema."

        return False, f"Unsupported postcondition type: {self.condition_type}"

    @classmethod
    def from_spec(cls, spec: Union[str, Dict[str, Any], TypedPostcondition]) -> TypedPostcondition:
        if isinstance(spec, cls):
            return spec
        if isinstance(spec, dict):
            return cls(**spec)
        if isinstance(spec, str):
            clean = spec.strip()
            m_struct = re.match(r"^(note|reminder|document|file):([^:]+):([a-zA-Z_]+)$", clean, re.IGNORECASE)
            if m_struct:
                etype, eid, estate = m_struct.group(1).lower(), m_struct.group(2).strip(), m_struct.group(3).lower()
                type_map = {
                    "note": PostconditionType.NOTE_STATE,
                    "reminder": PostconditionType.REMINDER_STATE,
                    "document": PostconditionType.DOCUMENT_STATE,
                    "file": PostconditionType.FILE_STATE,
                }
                if etype == "file":
                    return cls(
                        condition_type=type_map[etype],
                        target_path=eid,
                        expected_state=estate,
                        description=spec,
                    )
                return cls(
                    condition_type=type_map[etype],
                    entity_id=eid,
                    expected_state=estate,
                    description=spec,
                )

            m_note_del = re.search(r"note\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?\s+.*(?:deleted|removed)", clean, re.IGNORECASE)
            if m_note_del:
                return cls(
                    condition_type=PostconditionType.NOTE_STATE,
                    entity_id=m_note_del.group(1),
                    expected_state="deleted",
                    description=spec,
                )

            m_note_create = re.search(r"note\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?\s+.*(?:created|verified|persisted)", clean, re.IGNORECASE)
            if m_note_create:
                return cls(
                    condition_type=PostconditionType.NOTE_STATE,
                    entity_id=m_note_create.group(1),
                    expected_state="exists",
                    description=spec,
                )

            m_rem_comp = re.search(r"reminder\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?\s+.*(?:completed|done)", clean, re.IGNORECASE)
            if m_rem_comp:
                return cls(
                    condition_type=PostconditionType.REMINDER_STATE,
                    entity_id=m_rem_comp.group(1),
                    expected_state="completed",
                    description=spec,
                )

            m_rem_sched = re.search(r"reminder\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?\s+.*(?:scheduled|created|pending)", clean, re.IGNORECASE)
            if m_rem_sched:
                return cls(
                    condition_type=PostconditionType.REMINDER_STATE,
                    entity_id=m_rem_sched.group(1),
                    expected_state="scheduled",
                    description=spec,
                )

            return cls(
                condition_type=PostconditionType.UNSPECIFIED,
                expected_state="unknown",
                description=spec,
            )

        raise TypeError(f"Cannot construct TypedPostcondition from {type(spec)}")


class VerificationResult(BaseModel):
    """Detailed verification outcome including postcondition checks."""
    status: VerificationStatus
    is_satisfied: bool
    explanation: str
    completed_postconditions: List[str] = Field(default_factory=list)
    failed_postconditions: List[str] = Field(default_factory=list)


class OutcomeVerifier:
    """
    Verifies that executed step outcomes satisfy the user's objective
    by evaluating deterministic postconditions rather than naive status strings.
    """

    def verify(
        self,
        ctx: ExecutionContext,
        goal: str,
        tool_results: List[Dict[str, Any]],
        expected_postconditions: Optional[List[Union[str, Dict[str, Any], TypedPostcondition]]] = None,
    ) -> VerificationResult:
        """
        Evaluate execution results against explicit, deterministic postconditions.
        """
        from app.knowledge.repository import knowledge_repo

        # Audit no-tool executions: legitimate only when no postconditions were expected
        if not tool_results:
            if expected_postconditions:
                failed_reasons = []
                for exp in expected_postconditions:
                    p = TypedPostcondition.from_spec(exp) if not isinstance(exp, TypedPostcondition) else exp
                    failed_reasons.append(p.description or str(exp))
                return VerificationResult(
                    status=VerificationStatus.INCOMPLETE,
                    is_satisfied=False,
                    explanation=f"Illegitimate execution: no tool actions executed, but postconditions {failed_reasons} were required.",
                    failed_postconditions=failed_reasons,
                )
            return VerificationResult(
                status=VerificationStatus.COMPLETE,
                is_satisfied=True,
                explanation="No tool actions were required; synthesized from context.",
            )

        completed_checks: List[str] = []
        failed_checks: List[str] = []
        approvals_pending: List[str] = []
        errors: List[str] = []
        successful_tools: List[str] = []
        unknown_tools: List[str] = []

        for r in tool_results:
            st = r.get("status")
            tname = r.get("tool_name") or r.get("tool") or "unknown_tool"
            data = r.get("data") or {}

            if st == "awaiting_approval":
                approvals_pending.append(tname)
            elif st == "error":
                err_msg = r.get("error_message") or r.get("error") or "Unknown error"
                errors.append(f"{tname}: {err_msg}")
                failed_checks.append(f"Tool {tname} failed with: {err_msg}")
            elif st == "success":
                successful_tools.append(tname)
                # Specific domain postcondition assertions verified against authoritative repository state
                if tname == "notes.delete":
                    nid = data.get("note_id") or data.get("result", {}).get("note_id")
                    if data.get("deleted") is True or data.get("result", {}).get("deleted") is True:
                        note = knowledge_repo.get_note(ctx, nid) if nid else None
                        if note is None or note.get("is_deleted") is True:
                            completed_checks.append(f"Note '{nid or 'target'}' confirmed deleted in repository.")
                        else:
                            failed_checks.append(f"Note '{nid}' still present/active in repository.")
                    else:
                        failed_checks.append("Note delete operation reported false or missing target.")
                elif tname == "notes.create":
                    nid = data.get("note_id") or data.get("result", {}).get("note_id")
                    if nid:
                        note = knowledge_repo.get_note(ctx, nid)
                        if note:
                            completed_checks.append(f"Note '{nid}' created and verified in repository.")
                        else:
                            failed_checks.append(f"Note '{nid}' not found in repository.")
                    else:
                        failed_checks.append("Note creation did not return a valid note_id.")
                elif tname == "reminders.create":
                    rid = data.get("reminder_id") or data.get("result", {}).get("reminder_id")
                    if rid:
                        rems = knowledge_repo.list_reminders(ctx)
                        if any(rem.get("reminder_id") == rid for rem in rems):
                            completed_checks.append(f"Reminder '{rid}' scheduled and verified in repository.")
                        else:
                            failed_checks.append(f"Reminder '{rid}' not found in repository.")
                    else:
                        failed_checks.append("Reminder creation did not return a valid reminder_id.")
                elif tname == "reminders.complete":
                    rid = data.get("reminder_id") or data.get("result", {}).get("reminder_id")
                    if data.get("completed") is True or data.get("result", {}).get("completed") is True:
                        rems = knowledge_repo.list_reminders(ctx, status="COMPLETED")
                        if not rid or any(rem.get("reminder_id") == rid for rem in rems):
                            completed_checks.append("Reminder confirmed COMPLETED in repository.")
                        else:
                            failed_checks.append(f"Reminder '{rid}' not marked COMPLETED in repository.")
                    else:
                        failed_checks.append("Reminder completion failed or target not found.")
                elif tname in (
                    "calendar.list_events", "calendar.get_event", "notes.list",
                    "notes.read", "reminders.list", "filesystem.read_file",
                    "filesystem.write_file", "fetch.get_url", "sqlite.read_query",
                ):
                    completed_checks.append(f"Tool {tname} executed successfully.")
                else:
                    # Uncheckable external tool: mark UNKNOWN rather than claiming verified success
                    unknown_tools.append(tname)
                    completed_checks.append(f"Tool {tname} returned output (unverified domain postcondition: UNKNOWN).")

        # Evaluate explicit expected_postconditions deterministically
        if expected_postconditions:
            for exp in expected_postconditions:
                try:
                    postcond = (
                        exp if isinstance(exp, TypedPostcondition)
                        else TypedPostcondition.from_spec(exp)
                    )
                    ok, msg = postcond.evaluate(ctx)
                    if ok:
                        completed_checks.append(msg)
                    else:
                        failed_checks.append(msg)
                except Exception as p_err:
                    failed_checks.append(f"Postcondition evaluation error for '{exp}': {p_err}")

        # 1. Blocked by required approval
        if approvals_pending:
            return VerificationResult(
                status=VerificationStatus.BLOCKED,
                is_satisfied=False,
                explanation=f"Action(s) {approvals_pending} require human approval before completion.",
                completed_postconditions=completed_checks,
                failed_postconditions=failed_checks,
            )

        # 2. Total or Partial Failure
        if errors or failed_checks:
            if successful_tools or completed_checks:
                return VerificationResult(
                    status=VerificationStatus.INCOMPLETE,
                    is_satisfied=False,
                    explanation=f"Compound workflow partially completed. Failed checks: {'; '.join(failed_checks)}",
                    completed_postconditions=completed_checks,
                    failed_postconditions=failed_checks,
                )
            return VerificationResult(
                status=VerificationStatus.FAILED,
                is_satisfied=False,
                explanation=f"Execution failed with error(s): {'; '.join(errors or failed_checks)}",
                completed_postconditions=completed_checks,
                failed_postconditions=failed_checks,
            )

        # 3. Uncheckable / Ambiguous tools without authoritative repository verification
        if unknown_tools and (set(successful_tools) == set(unknown_tools) or not any("confirmed" in c or "verified" in c for c in completed_checks)):
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                is_satisfied=False,
                explanation=f"Execution outcome cannot be verified: tools {unknown_tools} lack verifiable domain postconditions.",
                completed_postconditions=completed_checks,
                failed_postconditions=failed_checks,
            )

        return VerificationResult(
            status=VerificationStatus.COMPLETE,
            is_satisfied=True,
            explanation=f"All requested operations ({', '.join(successful_tools)}) completed and verified successfully.",
            completed_postconditions=completed_checks,
            failed_postconditions=failed_checks,
        )


# Global default verifier
verifier = OutcomeVerifier()
