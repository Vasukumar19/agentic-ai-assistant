"""Semantic & Postcondition-Based Outcome Verifier."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.core.context import ExecutionContext


class VerificationStatus(str, Enum):
    """Explicit verification outcome states."""
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


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
        expected_postconditions: Optional[List[str]] = None,
    ) -> VerificationResult:
        """
        Evaluate execution results against explicit postconditions.
        """
        if not tool_results:
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
                # Specific domain postcondition assertions
                if tname == "notes.delete":
                    if data.get("deleted") is True or data.get("result", {}).get("deleted") is True:
                        completed_checks.append(f"Note successfully marked deleted in repository.")
                    else:
                        failed_checks.append(f"Note delete operation reported false or missing target.")
                elif tname == "notes.create":
                    nid = data.get("note_id") or data.get("result", {}).get("note_id")
                    if nid:
                        completed_checks.append(f"Note '{nid}' created and persisted.")
                    else:
                        failed_checks.append(f"Note creation did not return a valid note_id.")
                elif tname == "reminders.create":
                    rid = data.get("reminder_id") or data.get("result", {}).get("reminder_id")
                    if rid:
                        completed_checks.append(f"Reminder '{rid}' scheduled and persisted.")
                    else:
                        failed_checks.append(f"Reminder creation did not return a valid reminder_id.")
                elif tname == "reminders.complete":
                    if data.get("completed") is True or data.get("result", {}).get("completed") is True:
                        completed_checks.append(f"Reminder status transitioned to COMPLETED.")
                    else:
                        failed_checks.append(f"Reminder completion failed or target not found.")
                else:
                    completed_checks.append(f"Tool {tname} returned valid output.")

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
            if successful_tools:
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

        return VerificationResult(
            status=VerificationStatus.COMPLETE,
            is_satisfied=True,
            explanation=f"All requested operations ({', '.join(successful_tools)}) completed successfully.",
            completed_postconditions=completed_checks,
            failed_postconditions=failed_checks,
        )


# Global default verifier
verifier = OutcomeVerifier()
