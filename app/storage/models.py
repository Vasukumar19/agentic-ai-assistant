"""SQLAlchemy ORM models implementing the normalized V2 relational data model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.storage.database import Base


def _utc_now():
    return datetime.now(timezone.utc)


class UserModel(Base):
    """Users & Tenant Accounts."""
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    timezone = Column(String(64), default="UTC")
    preferences = Column(Text, default="{}")  # JSON string
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    # Relationships
    conversations = relationship("ConversationModel", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("DocumentModel", back_populates="user", cascade="all, delete-orphan")
    profile_facts = relationship("ProfileFactModel", back_populates="user", cascade="all, delete-orphan")
    notes = relationship("NoteModel", back_populates="user", cascade="all, delete-orphan")
    reminders = relationship("ReminderModel", back_populates="user", cascade="all, delete-orphan")


class ConversationModel(Base):
    """Conversation Threads."""
    __tablename__ = "conversations"

    session_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), default="New Conversation")
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    # Relationships
    user = relationship("UserModel", back_populates="conversations")
    messages = relationship("MessageModel", back_populates="conversation", cascade="all, delete-orphan")
    executions = relationship("ExecutionModel", back_populates="conversation", cascade="all, delete-orphan")


class MessageModel(Base):
    """Conversation Messages."""
    __tablename__ = "messages"

    message_id = Column(String(64), primary_key=True)
    session_id = Column(String(64), ForeignKey("conversations.session_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    citations = Column(Text, default="[]")  # JSON array of CitationRecord dicts
    token_usage = Column(Text, default="{}")  # JSON dict
    correlation_id = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    # Relationships
    conversation = relationship("ConversationModel", back_populates="messages")


class DocumentModel(Base):
    """Ingested Documents Metadata."""
    __tablename__ = "documents"

    document_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)
    mime_type = Column(String(128), default="text/plain")
    content_hash = Column(String(64), nullable=False)  # SHA-256
    total_chunks = Column(Integer, default=0)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_user_content_hash"),
    )

    # Relationships
    user = relationship("UserModel", back_populates="documents")
    chunks = relationship("DocumentChunkModel", back_populates="document", cascade="all, delete-orphan")


class DocumentChunkModel(Base):
    """Document Text Chunks & Vector Representation."""
    __tablename__ = "document_chunks"

    chunk_id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=True)  # JSON array of float vector
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    # Relationships
    document = relationship("DocumentModel", back_populates="chunks")


class ProfileFactModel(Base):
    """Structured Personal Knowledge Profile Facts."""
    __tablename__ = "profile_facts"

    fact_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(64), default="general")
    fact_key = Column(String(128), nullable=False)
    fact_value = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    source_session_id = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint("user_id", "fact_key", name="uq_user_fact_key"),
    )

    # Relationships
    user = relationship("UserModel", back_populates="profile_facts")


class SemanticMemoryModel(Base):
    """Unstructured Long-Term Semantic Memories."""
    __tablename__ = "semantic_memories"

    memory_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    memory_text = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=False)  # JSON array of float vector
    source_message_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)


class NoteModel(Base):
    """User Personal Notes."""
    __tablename__ = "notes"

    note_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    # Relationships
    user = relationship("UserModel", back_populates="notes")


class ReminderModel(Base):
    """Scheduled Reminders."""
    __tablename__ = "reminders"

    reminder_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(32), default="PENDING", index=True)  # PENDING | COMPLETED | CANCELLED
    recurrence_rule = Column(String(128), nullable=True)
    delivery_channel = Column(String(64), default="CLI")
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    delivery_attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    delivery_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    # Relationships
    user = relationship("UserModel", back_populates="reminders")


class ExecutionModel(Base):
    """Durable Workflow Execution Ledger."""
    __tablename__ = "executions"

    execution_id = Column(String(64), primary_key=True)
    session_id = Column(String(64), ForeignKey("conversations.session_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    query = Column(Text, nullable=False)
    execution_mode = Column(String(32), default="FAST_PATH")  # FAST_PATH | DELIBERATE_PATH
    status = Column(String(32), default="RUNNING", index=True)  # RUNNING | AWAITING_APPROVAL | COMPLETED | FAILED
    active_plan = Column(Text, nullable=True)  # JSON serialized Plan
    final_answer = Column(Text, nullable=True)
    total_tokens = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("ConversationModel", back_populates="executions")
    steps = relationship("ExecutionStepModel", back_populates="execution", cascade="all, delete-orphan")
    approvals = relationship("ActionApprovalModel", back_populates="execution", cascade="all, delete-orphan")


class ExecutionStepModel(Base):
    """Discrete Step Execution Records within a Turn."""
    __tablename__ = "execution_steps"

    step_id = Column(String(64), primary_key=True)
    execution_id = Column(String(64), ForeignKey("executions.execution_id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    tool_name = Column(String(128), nullable=True)
    tool_arguments = Column(Text, nullable=True)  # JSON string
    tool_result = Column(Text, nullable=True)  # JSON string
    status = Column(String(32), default="SUCCESS")  # SUCCESS | FAILED | AWAITING_APPROVAL
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    # Relationships
    execution = relationship("ExecutionModel", back_populates="steps")


class ActionApprovalModel(Base):
    """Cryptographically Bound Human Confirmation Records."""
    __tablename__ = "action_approvals"

    action_id = Column(String(64), primary_key=True)
    execution_id = Column(String(64), ForeignKey("executions.execution_id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(128), nullable=False)
    arguments_payload = Column(Text, nullable=False)  # JSON string
    arguments_hash = Column(String(64), nullable=False)
    approval_token = Column(String(128), unique=True, nullable=False, index=True)
    summary = Column(String(512), nullable=True)
    risk_level = Column(String(32), default="DESTRUCTIVE")
    status = Column(String(32), default="PENDING", index=True)  # PENDING | APPROVED | CONSUMED | REJECTED | EXPIRED
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_outcome = Column(Text, nullable=True)

    # Relationships
    execution = relationship("ExecutionModel", back_populates="approvals")
