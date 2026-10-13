"""ExecutionContext: Immutable execution identity threaded through all system layers."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any


def _gen_id(prefix: str) -> str:
    """Generate a unique identifier with typed prefix."""
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ExecutionContext:
    """
    Immutable execution context that establishes identity, tenant isolation,
    and distributed trace correlation across all layers.
    """
    user_id: str
    session_id: str
    execution_id: str
    plan_id: Optional[str] = None
    step_id: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: _gen_id("cor"))
    created_at: str = field(default_factory=_utc_now_iso)

    @classmethod
    def create(
        cls,
        user_id: str = "usr_default",
        session_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> ExecutionContext:
        """Factory method to instantiate a fresh execution context."""
        return cls(
            user_id=user_id or "usr_default",
            session_id=session_id or _gen_id("ses"),
            execution_id=execution_id or _gen_id("exec"),
            correlation_id=correlation_id or _gen_id("cor"),
            plan_id=plan_id,
            step_id=step_id,
            created_at=_utc_now_iso(),
        )

    def with_step(self, step_id: str, plan_id: Optional[str] = None) -> ExecutionContext:
        """Derive a new context for a specific execution step."""
        return ExecutionContext(
            user_id=self.user_id,
            session_id=self.session_id,
            execution_id=self.execution_id,
            correlation_id=self.correlation_id,
            plan_id=plan_id or self.plan_id,
            step_id=step_id,
            created_at=self.created_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return asdict(self)
