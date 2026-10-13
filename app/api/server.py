"""FastAPI Application Server for Personal Knowledge & Planning Assistant."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.assistant import assistant_app
from app.core.config import settings
from app.core.context import ExecutionContext
from app.knowledge.repository import knowledge_repo

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Personal Knowledge & Planning Assistant API",
    description="Production-grade API providing Chat, Today, My Knowledge, Reminders, and Settings.",
    version="2.0.0",
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Request & Response Models
# ==============================================================================

class ChatRequest(BaseModel):
    query: str
    user_id: str = "usr_default"
    session_id: Optional[str] = None
    approval_token: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    route: str
    execution_status: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    correlation_id: str
    user_id: str


class ProfileFactRequest(BaseModel):
    key: str
    value: str


class NoteCreateRequest(BaseModel):
    title: str
    content: str


class ReminderCreateRequest(BaseModel):
    title: str
    due_date: str


class ApproveActionRequest(BaseModel):
    approval_token: str
    action_id: Optional[str] = None
    user_id: str = "usr_default"


# ==============================================================================
# 1. Chat Endpoints
# ==============================================================================

@app.post("/api/chat", response_model=ChatResponse)
def execute_chat_query(req: ChatRequest):
    """Execute a conversational query across knowledge, schedule, and tools."""
    try:
        res = assistant_app.invoke(
            query=req.query,
            user_id=req.user_id,
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
            user_id=res.get("user_id", req.user_id),
        )
    except Exception as exc:
        logger.error("Chat execution error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Assistant execution failure: {str(exc)}",
        )


# ==============================================================================
# 2. Today: Daily Briefing & Commitments
# ==============================================================================

@app.get("/api/today")
def get_today_overview(user_id: str = "usr_default", date: Optional[str] = None):
    """Retrieve daily briefing, commitments, and preparation advice."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    query = f"Give me a comprehensive daily briefing for {target_date} with what I have scheduled and how I should prepare."
    res = assistant_app.invoke(query=query, user_id=user_id)
    return {
        "date": target_date,
        "briefing": res.get("answer", ""),
        "route": res.get("route"),
        "status": res.get("execution_status"),
    }


# ==============================================================================
# 3. My Knowledge: Profile Facts & Notes
# ==============================================================================

@app.get("/api/knowledge/facts")
def get_profile_facts(user_id: str = "usr_default"):
    """List all saved profile facts for the tenant."""
    ctx = ExecutionContext.create(user_id=user_id)
    facts = knowledge_repo.get_profile_facts(ctx)
    return {"facts": facts}


@app.post("/api/knowledge/facts")
def set_profile_fact(req: ProfileFactRequest, user_id: str = "usr_default"):
    """Store or update a profile fact."""
    ctx = ExecutionContext.create(user_id=user_id)
    knowledge_repo.set_profile_fact(ctx, key=req.key, value=req.value)
    return {"status": "saved", "key": req.key, "value": req.value}


@app.get("/api/knowledge/notes")
def list_notes(user_id: str = "usr_default"):
    """List all saved personal notes."""
    ctx = ExecutionContext.create(user_id=user_id)
    notes = knowledge_repo.list_notes(ctx)
    return {"notes": notes}


@app.post("/api/knowledge/notes")
def create_note(req: NoteCreateRequest, user_id: str = "usr_default"):
    """Create a new personal note."""
    ctx = ExecutionContext.create(user_id=user_id)
    nid = knowledge_repo.create_note(ctx, title=req.title, content=req.content)
    return {"status": "created", "note_id": nid}


@app.delete("/api/knowledge/notes/{note_id}")
def delete_note(note_id: str, user_id: str = "usr_default", approval_token: Optional[str] = None):
    """Delete a personal note (approval required)."""
    ctx = ExecutionContext.create(user_id=user_id)
    res = assistant_app.invoke(
        query=f"Delete note {note_id}",
        user_id=user_id,
        approval_token=approval_token,
    )
    return res


# ==============================================================================
# 4. Reminders
# ==============================================================================

@app.get("/api/reminders")
def list_reminders(user_id: str = "usr_default"):
    """List all pending and active reminders."""
    ctx = ExecutionContext.create(user_id=user_id)
    rems = knowledge_repo.list_reminders(ctx)
    return {"reminders": rems}


@app.post("/api/reminders")
def create_reminder(req: ReminderCreateRequest, user_id: str = "usr_default"):
    """Create a new reminder."""
    ctx = ExecutionContext.create(user_id=user_id)
    due_dt = datetime.now()
    try:
        due_dt = datetime.fromisoformat(req.due_date)
    except Exception:
        pass
    rid = knowledge_repo.create_reminder(ctx, title=req.title, due_date=due_dt)
    return {"status": "created", "reminder_id": rid}


@app.post("/api/reminders/{reminder_id}/complete")
def complete_reminder(reminder_id: str, user_id: str = "usr_default"):
    """Mark a reminder as completed."""
    ctx = ExecutionContext.create(user_id=user_id)
    ok = knowledge_repo.complete_reminder(ctx, reminder_id)
    return {"status": "completed" if ok else "not_found", "reminder_id": reminder_id}


# ==============================================================================
# 5. Approvals
# ==============================================================================

@app.post("/api/approvals/approve")
def approve_pending_action(req: ApproveActionRequest):
    """Execute a staged action by providing its cryptographic approval token."""
    res = assistant_app.invoke(
        query="Execute approved action",
        user_id=req.user_id,
        approval_token=req.approval_token,
    )
    return res


# ==============================================================================
# 6. Settings & Health
# ==============================================================================

@app.get("/api/settings")
def get_system_settings():
    """Retrieve system configuration and capability settings."""
    return {
        "architecture": "v2_modular_monolith",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "database": "sqlite_wal",
        "human_in_the_loop": "cryptographic_hmac_sha256",
        "ssrf_protection": "active",
        "filesystem_jail": "isolated_tenant_sandbox",
    }


@app.get("/healthz")
def healthcheck():
    """Liveness probe."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
