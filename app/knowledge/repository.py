"""Unified Knowledge Repository for Profile Facts, Notes, Reminders, and Document Chunks."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.context import ExecutionContext
from app.storage.database import get_session
from app.storage.models import (
    UserModel,
    ProfileFactModel,
    NoteModel,
    ReminderModel,
    DocumentModel,
    DocumentChunkModel,
)


def _ensure_user(session, user_id: str) -> UserModel:
    """Ensure user record exists in database."""
    user = session.get(UserModel, user_id)
    if not user:
        user = UserModel(
            user_id=user_id,
            email=f"{user_id}@local",
            full_name=user_id,
        )
        session.add(user)
        session.flush()
    return user


class KnowledgeRepository:
    """Transactional CRUD repository for all personal knowledge entities."""

    # --------------------------------------------------------------------------
    # Profile Facts
    # --------------------------------------------------------------------------

    def set_profile_fact(
        self,
        ctx: ExecutionContext,
        key: str,
        value: str,
        category: str = "general",
        confidence: float = 1.0,
    ) -> None:
        """Store or update a declarative biographical fact."""
        clean_key = key.strip().lower().replace(" ", "_")
        with get_session() as session:
            _ensure_user(session, ctx.user_id)
            fact = (
                session.query(ProfileFactModel)
                .filter_by(user_id=ctx.user_id, fact_key=clean_key)
                .first()
            )
            if fact:
                fact.fact_value = value
                fact.category = category
                fact.confidence = confidence
                fact.source_session_id = ctx.session_id
            else:
                fact = ProfileFactModel(
                    fact_id=f"fact_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}",
                    user_id=ctx.user_id,
                    category=category,
                    fact_key=clean_key,
                    fact_value=value,
                    confidence=confidence,
                    source_session_id=ctx.session_id,
                )
                session.add(fact)

    def get_profile_facts(self, ctx: ExecutionContext) -> Dict[str, str]:
        """Retrieve all active biographical profile facts for tenant."""
        with get_session() as session:
            facts = session.query(ProfileFactModel).filter_by(user_id=ctx.user_id).all()
            return {f.fact_key: f.fact_value for f in facts}

    def delete_profile_fact(self, ctx: ExecutionContext, key: str) -> bool:
        clean_key = key.strip().lower().replace(" ", "_")
        with get_session() as session:
            fact = (
                session.query(ProfileFactModel)
                .filter_by(user_id=ctx.user_id, fact_key=clean_key)
                .first()
            )
            if fact:
                session.delete(fact)
                return True
            return False

    # --------------------------------------------------------------------------
    # Personal Notes
    # --------------------------------------------------------------------------

    def create_note(self, ctx: ExecutionContext, title: str, content: str, note_id: Optional[str] = None) -> str:
        """Create a new personal note."""
        nid = note_id or f"note_{int(time.time()*1000)}_{uuid.uuid4().hex[:4]}"
        with get_session() as session:
            _ensure_user(session, ctx.user_id)
            note = NoteModel(
                note_id=nid,
                user_id=ctx.user_id,
                title=title,
                content=content,
            )
            session.add(note)
        return nid

    def list_notes(self, ctx: ExecutionContext, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """List user's notes."""
        with get_session() as session:
            query = session.query(NoteModel).filter_by(user_id=ctx.user_id)
            if not include_deleted:
                query = query.filter_by(is_deleted=False)
            notes = query.order_by(NoteModel.updated_at.desc()).all()
            return [
                {
                    "note_id": n.note_id,
                    "title": n.title,
                    "content": n.content,
                    "is_deleted": n.is_deleted,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                    "updated_at": n.updated_at.isoformat() if n.updated_at else None,
                }
                for n in notes
            ]

    def get_note(self, ctx: ExecutionContext, note_id: str) -> Optional[Dict[str, Any]]:
        """Get single note by ID."""
        with get_session() as session:
            n = session.query(NoteModel).filter_by(user_id=ctx.user_id, note_id=note_id).first()
            if not n or n.is_deleted:
                return None
            return {
                "note_id": n.note_id,
                "title": n.title,
                "content": n.content,
                "is_deleted": n.is_deleted,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "updated_at": n.updated_at.isoformat() if n.updated_at else None,
            }

    def delete_note(self, ctx: ExecutionContext, note_id: str, soft_delete: bool = True) -> bool:
        """Delete note (soft delete by default)."""
        with get_session() as session:
            n = session.query(NoteModel).filter_by(user_id=ctx.user_id, note_id=note_id).first()
            if not n:
                return False
            if soft_delete:
                n.is_deleted = True
                n.deleted_at = datetime.now(timezone.utc)
            else:
                session.delete(n)
            return True

    # --------------------------------------------------------------------------
    # Reminders
    # --------------------------------------------------------------------------

    def create_reminder(
        self,
        ctx: ExecutionContext,
        title: str,
        due_date: datetime,
        description: Optional[str] = None,
        recurrence_rule: Optional[str] = None,
        reminder_id: Optional[str] = None,
    ) -> str:
        """Create a scheduled reminder."""
        rid = reminder_id or f"rem_{int(time.time()*1000)}_{uuid.uuid4().hex[:4]}"
        with get_session() as session:
            _ensure_user(session, ctx.user_id)
            rem = ReminderModel(
                reminder_id=rid,
                user_id=ctx.user_id,
                title=title,
                description=description,
                due_date=due_date,
                status="PENDING",
                recurrence_rule=recurrence_rule,
            )
            session.add(rem)
        return rid

    def list_reminders(self, ctx: ExecutionContext, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List reminders, optionally filtered by status."""
        with get_session() as session:
            query = session.query(ReminderModel).filter_by(user_id=ctx.user_id)
            if status:
                query = query.filter_by(status=status.upper())
            rems = query.order_by(ReminderModel.due_date.asc()).all()
            return [
                {
                    "reminder_id": r.reminder_id,
                    "title": r.title,
                    "description": r.description,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "status": r.status,
                    "recurrence_rule": r.recurrence_rule,
                }
                for r in rems
            ]

    def complete_reminder(self, ctx: ExecutionContext, reminder_id: str) -> bool:
        """Mark reminder as completed."""
        with get_session() as session:
            r = session.query(ReminderModel).filter_by(user_id=ctx.user_id, reminder_id=reminder_id).first()
            if not r:
                return False
            r.status = "COMPLETED"
            return True

    # --------------------------------------------------------------------------
    # Documents & Ingested Chunks
    # --------------------------------------------------------------------------

    def save_document(
        self,
        ctx: ExecutionContext,
        filename: str,
        content: str,
        chunks: List[Dict[str, Any]],
        document_id: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> str:
        """Store an ingested document and its text chunks."""
        did = document_id or f"doc_{int(time.time()*1000)}_{uuid.uuid4().hex[:4]}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        with get_session() as session:
            _ensure_user(session, ctx.user_id)
            doc = DocumentModel(
                document_id=did,
                user_id=ctx.user_id,
                filename=filename,
                file_path=file_path,
                content_hash=content_hash,
                total_chunks=len(chunks),
            )
            session.add(doc)
            session.flush()

            for idx, c in enumerate(chunks):
                cid = c.get("chunk_id") or f"{did}_c{idx:03d}"
                chunk = DocumentChunkModel(
                    chunk_id=cid,
                    document_id=did,
                    user_id=ctx.user_id,
                    chunk_index=idx,
                    page_number=c.get("page_number", 1),
                    char_start=c.get("char_start", 0),
                    char_end=c.get("char_end", len(c.get("content", ""))),
                    content=c.get("content", ""),
                    embedding_json=json.dumps(c.get("embedding", [])) if c.get("embedding") else None,
                    metadata_json=json.dumps(c.get("metadata", {})),
                )
                session.add(chunk)

        return did

    def get_all_chunks(self, ctx: ExecutionContext) -> List[Dict[str, Any]]:
        """Retrieve all active document chunks for hybrid retrieval."""
        with get_session() as session:
            chunks = (
                session.query(DocumentChunkModel, DocumentModel.filename)
                .join(DocumentModel, DocumentChunkModel.document_id == DocumentModel.document_id)
                .filter(DocumentChunkModel.user_id == ctx.user_id)
                .all()
            )
            results = []
            for chunk_row, filename in chunks:
                emb = json.loads(chunk_row.embedding_json) if chunk_row.embedding_json else []
                meta = json.loads(chunk_row.metadata_json) if chunk_row.metadata_json else {}
                results.append({
                    "chunk_id": chunk_row.chunk_id,
                    "document_id": chunk_row.document_id,
                    "filename": filename,
                    "chunk_index": chunk_row.chunk_index,
                    "page_number": chunk_row.page_number,
                    "char_start": chunk_row.char_start,
                    "char_end": chunk_row.char_end,
                    "content": chunk_row.content,
                    "embedding": emb,
                    "metadata": meta,
                })
            return results


# Global repository instance
knowledge_repo = KnowledgeRepository()
