"""FastAPI Application Server for Personal Knowledge & Planning Assistant."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.assistant import assistant_app
from app.core.auth import UserPrincipal, get_current_principal, verify_resource_ownership
from app.core.config import settings
from app.core.context import ExecutionContext
from app.knowledge.repository import knowledge_repo

logger = logging.getLogger(__name__)

# Validate security configuration at startup
settings.validate_security_configuration()

app = FastAPI(
    title="Personal Knowledge & Planning Assistant API",
    description="Enterprise-grade local-first API with authenticated principal identity and cryptographic safety.",
    version="2.0.0",
)

# ------------------------------------------------------------------------------
# CORS Middleware: Explicit allowlist, rejecting wildcard with credentials
# ------------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# Standardized Public Error Response Schemas & Handlers
# ------------------------------------------------------------------------------

class APIErrorDetail(BaseModel):
    error_code: str
    message: str
    correlation_id: str
    timestamp: str


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    cor_id = getattr(request.state, "correlation_id", f"cor_{uuid.uuid4().hex[:8]}")
    err_detail = exc.detail
    if isinstance(err_detail, dict):
        err_code = err_detail.get("error_code", "HTTP_ERROR")
        msg = err_detail.get("message", "An HTTP error occurred.")
    else:
        err_code = "HTTP_ERROR"
        msg = str(err_detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": err_code,
            "message": msg,
            "correlation_id": cor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    cor_id = getattr(request.state, "correlation_id", f"cor_{uuid.uuid4().hex[:8]}")
    logger.error("Unhandled server exception [cor_id=%s]: %s", cor_id, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": f"An unexpected internal error occurred. Please reference correlation ID: {cor_id}",
            "correlation_id": cor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ------------------------------------------------------------------------------
# Strict Request Models (No caller-controlled user_id, length & format bounded)
# ------------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000, description="User prompt text")
    user_id: Optional[str] = Field(None, max_length=64)
    session_id: Optional[str] = Field(None, max_length=128)
    approval_token: Optional[str] = Field(None, max_length=256)


class ChatResponse(BaseModel):
    answer: str
    route: str
    execution_status: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    correlation_id: str
    user_id: str


class ProfileFactRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., min_length=1, max_length=4096)


class NoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1, max_length=50000)


class ReminderCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    due_date: str = Field(..., min_length=10, max_length=64, description="ISO 8601 scheduled due timestamp")

    @field_validator("due_date")
    @classmethod
    def validate_iso_due_date(cls, v: str) -> str:
        # Strict validation: reject malformed dates instead of silently replacing
        clean_v = v.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(clean_v)
        except ValueError:
            raise ValueError(f"Invalid due_date format '{v}'. Must be a valid ISO 8601 string (e.g. 2026-10-20T18:00:00Z).")
        return v


class ApproveActionRequest(BaseModel):
    approval_token: str = Field(..., min_length=1, max_length=256)
    action_id: Optional[str] = Field(None, max_length=128)
    user_id: Optional[str] = Field(None, max_length=64)
    decision: str = Field(default="APPROVE", pattern="^(APPROVE|REJECT)$")


# ==============================================================================
# 1. Chat Endpoints (Protected by Principal Authentication)
# ==============================================================================

@app.post("/api/chat", response_model=ChatResponse)
def execute_chat_query(
    req: ChatRequest,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """Execute conversational turn strictly bound to authenticated principal."""
    effective_user_id = principal.user_id
    if settings.AUTH_MODE in ("development", "testing") and req.user_id and principal.user_id == "usr_dev":
        effective_user_id = req.user_id

    try:
        res = assistant_app.invoke(
            query=req.query,
            user_id=effective_user_id,
            session_id=req.session_id,
            approval_token=req.approval_token,
        )
        return ChatResponse(
            answer=res.get("answer", ""),
            route=res.get("route", "FAST_INFO"),
            execution_status=res.get("execution_status", "completed"),
            citations=res.get("citations", []),
            pending_approval=res.get("pending_approval"),
            correlation_id=res.get("correlation_id", ""),
            user_id=effective_user_id,
        )
    except Exception as exc:
        logger.error("Chat turn failure for user %s: %s", principal.user_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "CHAT_EXECUTION_FAILURE",
                "message": "Assistant execution failed to complete.",
            },
        )


# ==============================================================================
# 2. Today: Daily Briefing & Commitments
# ==============================================================================

@app.get("/api/today")
def get_today_overview(
    date: Optional[str] = None,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """Retrieve daily briefing and commitments for authenticated principal."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    query = f"Give me a comprehensive daily briefing for {target_date} with what I have scheduled and how I should prepare."
    res = assistant_app.invoke(query=query, user_id=principal.user_id)
    return {
        "date": target_date,
        "briefing": res.get("answer", ""),
        "route": res.get("route"),
        "status": res.get("execution_status"),
    }


# ==============================================================================
# 3. My Knowledge: Profile Facts & Notes (Tenant Isolated)
# ==============================================================================

@app.get("/api/knowledge/facts")
def get_profile_facts(
    principal: UserPrincipal = Depends(get_current_principal),
):
    """List all saved profile facts for the authenticated tenant."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    facts = knowledge_repo.get_profile_facts(ctx)
    return {"facts": facts}


@app.post("/api/knowledge/facts")
def set_profile_fact(
    req: ProfileFactRequest,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """Store or update a profile fact for the authenticated tenant."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    knowledge_repo.set_profile_fact(ctx, key=req.key, value=req.value)
    return {"status": "saved", "key": req.key, "value": req.value}


@app.get("/api/knowledge/notes")
def list_notes(
    principal: UserPrincipal = Depends(get_current_principal),
):
    """List all saved personal notes belonging to the authenticated tenant."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    notes = knowledge_repo.list_notes(ctx)
    return {"notes": notes}


@app.post("/api/knowledge/notes")
def create_note(
    req: NoteCreateRequest,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """Create a new personal note for the authenticated tenant."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    nid = knowledge_repo.create_note(ctx, title=req.title, content=req.content)
    return {"status": "created", "note_id": nid}


@app.delete("/api/knowledge/notes/{note_id}")
def delete_note(
    note_id: str,
    approval_token: Optional[str] = None,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """Delete a personal note belonging to the authenticated tenant."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    # Check note ownership
    note = knowledge_repo.get_note(ctx, note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOTE_NOT_FOUND", "message": f"Note '{note_id}' does not exist or was deleted."},
        )

    res = assistant_app.invoke(
        query=f"Delete note {note_id}",
        user_id=principal.user_id,
        approval_token=approval_token,
    )
    return res


# ==============================================================================
# 4. Reminders (Tenant Isolated & Strict Due Date Handling)
# ==============================================================================

@app.get("/api/reminders")
def list_reminders(
    principal: UserPrincipal = Depends(get_current_principal),
):
    """List all pending and active reminders for authenticated principal."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    rems = knowledge_repo.list_reminders(ctx)
    return {"reminders": rems}


@app.post("/api/reminders")
def create_reminder(
    req: ReminderCreateRequest,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """Create a new scheduled reminder with validated UTC instant."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    clean_date = req.due_date.replace("Z", "+00:00")
    try:
        due_dt = datetime.fromisoformat(clean_date)
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_DATE", "message": f"Could not parse due_date: {exc}"},
        )

    rid = knowledge_repo.create_reminder(ctx, title=req.title, due_date=due_dt)
    return {"status": "created", "reminder_id": rid, "due_date": due_dt.isoformat()}


@app.post("/api/reminders/{reminder_id}/complete")
def complete_reminder(
    reminder_id: str,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """Mark a reminder as completed if owned by authenticated principal."""
    ctx = ExecutionContext.create(user_id=principal.user_id)
    ok = knowledge_repo.complete_reminder(ctx, reminder_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "REMINDER_NOT_FOUND", "message": f"Reminder '{reminder_id}' not found."},
        )
    return {"status": "completed", "reminder_id": reminder_id}


# ==============================================================================
# 5. Approvals (Atomic & Bound to Action & Authenticated Principal)
# ==============================================================================

@app.post("/api/approvals/approve")
def approve_pending_action(
    req: ApproveActionRequest,
    principal: UserPrincipal = Depends(get_current_principal),
):
    """
    Validate and execute a staged action strictly bound to action_id and authenticated tenant.
    Resumes exact approved action without replanning.
    """
    effective_user_id = principal.user_id
    if settings.AUTH_MODE in ("development", "testing") and req.user_id and principal.user_id == "usr_dev":
        effective_user_id = req.user_id

    ctx = ExecutionContext.create(user_id=effective_user_id)
    from app.storage.database import get_session
    from app.storage.models import ActionApprovalModel

    # 1. Lookup pending record to verify ownership and find tool_name & arguments
    with get_session() as session:
        rec = session.query(ActionApprovalModel).filter(
            ActionApprovalModel.approval_token == req.approval_token,
        ).first()
        if not rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "APPROVAL_NOT_FOUND", "message": "Approval token not found."},
            )
        if rec.user_id != effective_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error_code": "APPROVAL_DENIED", "message": "User does not own this approval."},
            )
        if req.action_id and rec.action_id != req.action_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "ACTION_ID_MISMATCH", "message": "Action ID mismatch."},
            )
        tool_name = rec.tool_name
        act_id = rec.action_id
        try:
            import json
            args_dict = json.loads(rec.arguments_payload)
        except Exception:
            args_dict = {}

    # If decision is REJECT, mark rejected
    if req.decision.upper() in ("REJECT", "NO", "DENY"):
        with get_session() as session:
            rec = session.get(ActionApprovalModel, act_id)
            if rec and rec.status == "PENDING":
                rec.status = "REJECTED"
                rec.decided_at = datetime.now(timezone.utc)
        return {
            "status": "rejected",
            "execution_status": "rejected",
            "action_id": act_id,
            "tool_name": tool_name,
            "answer": f"Action '{tool_name}' was rejected by user.",
        }

    # 2. Dispatch directly through gateway (which atomically validates and consumes token)
    from app.gateway.dispatcher import gateway
    res = gateway.dispatch(
        ctx=ctx,
        tool_name=tool_name,
        arguments=args_dict,
        approval_token=req.approval_token,
        action_id=act_id,
    )

    if res.status != "success":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "APPROVAL_EXECUTION_FAILED", "message": res.error_message},
        )

    action_desc = "deleted" if "delete" in tool_name else "executed"
    return {
        "status": "executed",
        "execution_status": "completed",
        "action_id": act_id,
        "tool_name": tool_name,
        "answer": f"Approved action '{tool_name}' has been successfully {action_desc}.",
        "tool_result": res.model_dump(),
    }


# ==============================================================================
# 6. Settings & Health (Safe, Non-Leaking)
# ==============================================================================

@app.get("/api/settings")
def get_system_settings():
    """Retrieve non-sensitive system capability settings."""
    return {
        "architecture": "v2_modular_monolith",
        "environment": settings.ENVIRONMENT,
        "auth_mode": settings.AUTH_MODE,
        "database": "sqlite_wal",
        "human_in_the_loop": "cryptographic_hmac_sha256",
        "ssrf_protection": "active",
        "filesystem_jail": "isolated_tenant_sandbox",
    }


@app.get("/healthz")
def healthcheck():
    """Liveness probe."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
