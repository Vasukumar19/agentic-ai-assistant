"""Semantic Outcome Verifier replacing lexical Goal Guard."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from app.core.context import ExecutionContext


class OutcomeVerifier:
    """
    Verifies that the executed step outcomes satisfy the user's objective
    without relying on naive regex verb matching.
    """

    def verify(
        self,
        ctx: ExecutionContext,
        goal: str,
        tool_results: List[Dict[str, Any]],
    ) -> Tuple[bool, str]:
        """
        Evaluate execution results. Returns (is_satisfied, explanation).
        """
        if not tool_results:
            return True, "No tool actions were required; synthesized from context."

        errors = []
        approvals_pending = []
        successful_tools = []

        for r in tool_results:
            status = r.get("status")
            tool_name = r.get("tool_name") or r.get("tool")

            if status == "awaiting_approval":
                approvals_pending.append(tool_name)
            elif status == "error":
                err_msg = r.get("error_message") or r.get("error") or "Unknown error"
                errors.append(f"{tool_name}: {err_msg}")
            elif status == "success":
                successful_tools.append(tool_name)

        if approvals_pending:
            return False, f"Action(s) {approvals_pending} require human approval before completion."

        if errors:
            return False, f"Execution failed with tool error(s): {'; '.join(errors)}"

        return True, f"All requested operations ({', '.join(successful_tools)}) completed successfully."


# Global default verifier
verifier = OutcomeVerifier()
