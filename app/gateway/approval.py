"""Cryptographically Bound Human-In-The-Loop Approval Token Engine."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.context import ExecutionContext
from app.gateway.manifest import SideEffectLevel
from app.storage.database import get_session
from app.storage.models import ActionApprovalModel


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
        self.secret_key = (secret_key or settings.APPROVAL_HMAC_SECRET).encode("utf-8")

    def generate_token(
        self,
        action_id: str,
        user_id: str,
        tool_name: str,
        args_hash: str,
        expires_timestamp: int,
    ) -> str:
        """Create HMAC-SHA256 signature token bound to action identity and parameters."""
        payload = f"{action_id}:{user_id}:{tool_name}:{args_hash}:{expires_timestamp}".encode("utf-8")
        sig = hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()
        return f"tok_{action_id[:8]}_{sig[:24]}"

    def verify_token(
        self,
        action_id: str,
        user_id: str,
        tool_name: str,
        args_hash: str,
        expires_timestamp: int,
        token: str,
    ) -> bool:
        """Verify HMAC-SHA256 token against payload parameters."""
        expected = self.generate_token(action_id, user_id, tool_name, args_hash, expires_timestamp)
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
        action_id = f"act_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        args_hash = _hash_args(arguments)
        exp_s = expires_seconds or settings.APPROVAL_EXPIRATION_SECONDS
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=exp_s)
        expires_ts = int(expires_at.timestamp())

        token = self.generate_token(
            action_id=action_id,
            user_id=ctx.user_id,
            tool_name=tool_name,
            args_hash=args_hash,
            expires_timestamp=expires_ts,
        )

        with get_session() as session:
            from app.storage.models import UserModel
            user = session.get(UserModel, ctx.user_id)
            if not user:
                user = UserModel(
                    user_id=ctx.user_id,
                    email=f"{ctx.user_id}@local",
                    full_name=ctx.user_id,
                )
                session.add(user)
                session.flush()

            record = ActionApprovalModel(
                action_id=action_id,
                execution_id=None,
                user_id=ctx.user_id,
                tool_name=tool_name,
                arguments_payload=_canonical_json(arguments),
                arguments_hash=args_hash,
                approval_token=token,
                summary=summary,
                status="PENDING",
                expires_at=expires_at,
            )
            session.add(record)

        return action_id, token

    def validate_and_consume(
        self,
        ctx: ExecutionContext,
        approval_token: str,
        decision: str,  # "APPROVE" | "REJECT"
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate pending approval token against database and expiration.
        Returns (is_authorized, tool_name, approved_arguments).
        """
        now = datetime.now(timezone.utc)
        with get_session() as session:
            record = (
                session.query(ActionApprovalModel)
                .filter_by(approval_token=approval_token, status="PENDING")
                .first()
            )
            if not record:
                return False, None, None

            # Verify tenant match
            if record.user_id != ctx.user_id:
                return False, None, None

            # Verify expiration
            # SQLite stores naive or aware datetimes, normalize for comparison
            exp = record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                record.status = "EXPIRED"
                return False, None, None

            # Verify cryptographic signature
            args_dict = json.loads(record.arguments_payload)
            is_valid_sig = self.verify_token(
                action_id=record.action_id,
                user_id=record.user_id,
                tool_name=record.tool_name,
                args_hash=record.arguments_hash,
                expires_timestamp=int(exp.timestamp()),
                token=approval_token,
            )
            if not is_valid_sig:
                record.status = "REJECTED"
                return False, None, None

            # Handle Decision
            if decision.upper() in ("APPROVE", "CONFIRM", "YES"):
                record.status = "APPROVED"
                record.decided_at = now
                return True, record.tool_name, args_dict
            else:
                record.status = "REJECTED"
                record.decided_at = now
                return False, record.tool_name, args_dict


# Global default engine instance
approval_engine = ApprovalTokenEngine()
