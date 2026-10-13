"""Cryptographically Bound Human-In-The-Loop Approval Token Engine."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.context import ExecutionContext
from app.gateway.manifest import SideEffectLevel
from app.storage.database import get_session
from app.storage.models import ActionApprovalModel

logger = logging.getLogger(__name__)


def _canonical_json(data: Dict[str, Any]) -> str:
    """Produce deterministic canonical JSON string for hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _hash_args(args: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of canonical arguments."""
    return hashlib.sha256(_canonical_json(args).encode("utf-8")).hexdigest()


class ApprovalTokenEngine:
    """
    Manages generation, cryptographic verification, and lifecycle tracking
    for actions requiring human confirmation.
    """

    def __init__(self, secret_key: Optional[str] = None):
        self._custom_secret = secret_key

    @property
    def secret_key(self) -> bytes:
        if self._custom_secret:
            return self._custom_secret.encode("utf-8")
        return settings.get_approval_hmac_secret().encode("utf-8")

    def generate_token(
        self,
        action_id: str,
        user_id: str,
        tool_name: str,
        args_hash: str,
        risk_level: str,
        expires_timestamp: int,
    ) -> str:
        """Create HMAC-SHA256 signature token bound to action identity and parameters."""
        payload = f"{action_id}:{user_id}:{tool_name}:{args_hash}:{risk_level}:{expires_timestamp}".encode("utf-8")
        sig = hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()
        # Full 64 hex characters HMAC digest
        return f"tok_{action_id}_{sig}"

    def verify_token(
        self,
        action_id: str,
        user_id: str,
        tool_name: str,
        args_hash: str,
        risk_level: str,
        expires_timestamp: int,
        token: str,
    ) -> bool:
        """Verify HMAC-SHA256 token against payload parameters in constant time."""
        expected = self.generate_token(
            action_id=action_id,
            user_id=user_id,
            tool_name=tool_name,
            args_hash=args_hash,
            risk_level=risk_level,
            expires_timestamp=expires_timestamp,
        )
        return hmac.compare_digest(expected, token)

    def stage_approval(
        self,
        ctx: ExecutionContext,
        tool_name: str,
        arguments: Dict[str, Any],
        summary: str,
        risk_level: SideEffectLevel = SideEffectLevel.DESTRUCTIVE,
        expires_seconds: Optional[int] = None,
    ) -> Tuple[str, str]:
        """
        Stage an approval intent to the database and generate a secure token.
        Returns (action_id, approval_token).
        """
        action_id = f"act_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        args_hash = _hash_args(arguments)
        risk_val = risk_level.value if hasattr(risk_level, "value") else str(risk_level)
        exp_s = expires_seconds or settings.APPROVAL_EXPIRATION_SECONDS
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=exp_s)
        expires_ts = int(expires_at.timestamp())

        token = self.generate_token(
            action_id=action_id,
            user_id=ctx.user_id,
            tool_name=tool_name,
            args_hash=args_hash,
            risk_level=risk_val,
            expires_timestamp=expires_ts,
        )

        with get_session() as session:
            from app.storage.models import UserModel, ExecutionModel
            user = session.get(UserModel, ctx.user_id)
            if not user:
                user = UserModel(
                    user_id=ctx.user_id,
                    email=f"{ctx.user_id}@local",
                    full_name=ctx.user_id,
                )
                session.add(user)
                session.flush()

            exec_row = session.get(ExecutionModel, ctx.execution_id) if ctx.execution_id else None
            effective_exec_id = exec_row.execution_id if exec_row else None

            record = ActionApprovalModel(
                action_id=action_id,
                execution_id=effective_exec_id,
                user_id=ctx.user_id,
                tool_name=tool_name,
                arguments_payload=_canonical_json(arguments),
                arguments_hash=args_hash,
                approval_token=token,
                summary=summary,
                risk_level=risk_val,
                status="PENDING",
                expires_at=expires_at,
            )
            session.add(record)

        return action_id, token

    def validate_and_consume(
        self,
        ctx: ExecutionContext,
        approval_token: str,
        decision: str = "APPROVE",  # "APPROVE" | "REJECT"
        action_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate pending approval token against database, argument hash, and expiration.
        Performs an atomic state transition to prevent concurrent consumption or replay.
        Returns (is_authorized, tool_name, approved_arguments).
        """
        now = datetime.now(timezone.utc)
        with get_session() as session:
            query = session.query(ActionApprovalModel).filter(
                ActionApprovalModel.approval_token == approval_token
            )
            if action_id:
                query = query.filter(ActionApprovalModel.action_id == action_id)

            record = query.first()
            if not record:
                logger.warning("Approval record not found for token: %s", approval_token[:16])
                return False, None, None

            # Verify tenant match
            if record.user_id != ctx.user_id:
                logger.warning("Approval tenant mismatch: record=%s, ctx=%s", record.user_id, ctx.user_id)
                return False, None, None

            # Verify pending status
            if record.status != "PENDING":
                logger.warning("Approval record already transitioned: status=%s", record.status)
                return False, None, None

            # Verify expiration
            exp = record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                record.status = "EXPIRED"
                return False, None, None

            # Re-hash stored canonical arguments to verify DB payload integrity
            try:
                args_dict = json.loads(record.arguments_payload)
            except Exception:
                logger.error("Failed to parse stored arguments payload for action %s", record.action_id)
                record.status = "REJECTED"
                return False, None, None

            recomputed_hash = _hash_args(args_dict)
            if not hmac.compare_digest(recomputed_hash, record.arguments_hash):
                logger.error("Arguments hash tampering detected for action %s!", record.action_id)
                record.status = "REJECTED"
                return False, None, None

            # Verify cryptographic signature
            is_valid_sig = self.verify_token(
                action_id=record.action_id,
                user_id=record.user_id,
                tool_name=record.tool_name,
                args_hash=record.arguments_hash,
                risk_level=record.risk_level or "DESTRUCTIVE",
                expires_timestamp=int(exp.timestamp()),
                token=approval_token,
            )
            if not is_valid_sig:
                logger.warning("Cryptographic signature mismatch for action %s", record.action_id)
                record.status = "REJECTED"
                return False, None, None

            # Atomic State Transition via conditional UPDATE to claim execution lock
            target_status = "EXECUTING" if decision.upper() in ("APPROVE", "CONFIRM", "YES") else "REJECTED"
            updated = (
                session.query(ActionApprovalModel)
                .filter(
                    ActionApprovalModel.action_id == record.action_id,
                    ActionApprovalModel.status == "PENDING",
                )
                .update(
                    {
                        "status": target_status,
                        "decided_at": now,
                    },
                    synchronize_session="fetch",
                )
            )

            if updated == 0:
                logger.warning("Concurrent approval claim collision for action %s", record.action_id)
                return False, None, None

            if target_status == "EXECUTING":
                return True, record.tool_name, args_dict
            return False, record.tool_name, args_dict

    def get_action_id_by_token(self, approval_token: str) -> Optional[str]:
        """Look up the staged action_id associated with an approval token."""
        with get_session() as session:
            rec = session.query(ActionApprovalModel).filter_by(approval_token=approval_token).first()
            return rec.action_id if rec else None

    def record_execution_outcome(
        self,
        action_id: str,
        status: str,
        outcome_data: Optional[str] = None,
    ) -> None:
        """Record the post-execution outcome of an approved action."""
        now = datetime.now(timezone.utc)
        normalized_status = (
            "COMPLETED" if status in ("SUCCESS", "COMPLETED")
            else "FAILED" if status in ("FAILED", "ERROR")
            else status
        )
        with get_session() as session:
            rec = session.get(ActionApprovalModel, action_id)
            if rec:
                rec.status = normalized_status
                rec.executed_at = now
                rec.execution_outcome = outcome_data or status

    def recover_stale_executing_approvals(self, timeout_seconds: int = 300) -> int:
        """
        Recover actions left in EXECUTING state due to process crash/restart.
        Transitions state to UNCERTAIN to prevent dangling locks.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        with get_session() as session:
            stale = (
                session.query(ActionApprovalModel)
                .filter(
                    ActionApprovalModel.status == "EXECUTING",
                    (ActionApprovalModel.decided_at <= cutoff) | (ActionApprovalModel.decided_at.is_(None)),
                )
                .update(
                    {
                        "status": "UNCERTAIN",
                        "execution_outcome": "Execution interrupted by system restart or timeout before completion confirmation.",
                    },
                    synchronize_session="fetch",
                )
            )
            return stale


# Global default engine instance
approval_engine = ApprovalTokenEngine()
