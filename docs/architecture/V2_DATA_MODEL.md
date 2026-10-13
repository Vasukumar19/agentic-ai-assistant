# V2 Data Model & Relational Storage Specification

**Author:** Principal AI Systems Architect & Core Platform Team  
**Date:** October 2026  
**Status:** Approved Specification  
**Engine:** SQLite (Local-First Edge Mode) / PostgreSQL with `pgvector` (Cloud/Server Mode)

---

## 1. Schema Overview & Entity-Relationship Architecture

The target V2 storage architecture eliminates flat, unindexed JSON files (`memory.json`, `chat_history.json`, `notes.json`, `calendar.json`, `reminders.json`) in favor of a normalized relational schema with vector extensions.

```text
┌──────────────┐       1:N       ┌───────────────────┐       1:N       ┌──────────────────┐
│    users     ├────────────────►│   conversations   ├────────────────►│     messages     │
└──────┬───────┘                 └───────────────────┘                 └──────────────────┘
       │
       │ 1:N
       ├────────────────► ┌───────────────────┐       1:N       ┌──────────────────┐
       │                  │     documents     ├────────────────►│ document_chunks  │
       │                  └───────────────────┘                 └──────────────────┘
       │ 1:N
       ├────────────────► ┌───────────────────┐
       │                  │   profile_facts   │
       │                  └───────────────────┘
       │ 1:N
       ├────────────────► ┌───────────────────┐
       │                  │ semantic_memories │
       │                  └───────────────────┘
       │ 1:N
       ├────────────────► ┌───────────────────┐
       │                  │       notes       │
       │                  └───────────────────┘
       │ 1:N
       ├────────────────► ┌───────────────────┐
       │                  │     reminders     │
       │                  └───────────────────┘
       │ 1:N
       ├────────────────► ┌───────────────────┐       1:N       ┌──────────────────┐
       │                  │    executions     ├────────────────►│ execution_steps  │
       │                  └─────────┬─────────┘                 └──────────────────┘
       │                            │ 1:N
       │                            ▼
       └────────────────► ┌───────────────────┐
                          │ action_approvals  │
                          └───────────────────┘
```

---

## 2. Table DDL Specifications

### 2.1 Identity & Conversational Sessions

```sql
-- Users & Tenant Accounts
CREATE TABLE users (
    user_id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    timezone VARCHAR(64) DEFAULT 'UTC',
    preferences JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Conversation Sessions (Threads)
CREATE TABLE conversations (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255) DEFAULT 'New Conversation',
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);

-- Conversation Message History
CREATE TABLE messages (
    message_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL, -- 'user', 'assistant', 'system', 'tool'
    content TEXT NOT NULL,
    citations JSONB DEFAULT '[]'::jsonb, -- Array of CitationRecord objects
    token_usage JSONB DEFAULT '{}'::jsonb,
    correlation_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_session ON messages(session_id, created_at ASC);
```

---

### 2.2 Documents & Verified Knowledge Chunks

```sql
-- Ingested Documents
CREATE TABLE documents (
    document_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512),
    mime_type VARCHAR(128) NOT NULL,
    content_hash VARCHAR(64) NOT NULL, -- SHA-256 for deduplication
    total_chunks INTEGER NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_documents_user_hash ON documents(user_id, content_hash);

-- Text Chunks with Vector Embeddings
CREATE TABLE document_chunks (
    chunk_id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384), -- sentence-transformers/all-MiniLM-L6-v2 (or 1536 for OpenAI)
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunks_doc ON document_chunks(document_id, chunk_index ASC);
CREATE INDEX idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

### 2.3 Personal Knowledge: Profile Facts & Semantic Memories

```sql
-- Structured Profile Facts (Declarative Key-Values)
CREATE TABLE profile_facts (
    fact_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL, -- 'role', 'preference', 'contact', 'biography'
    fact_key VARCHAR(128) NOT NULL, -- 'primary_language', 'office_location'
    fact_value TEXT NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source_session_id VARCHAR(64),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_profile_facts_user_key ON profile_facts(user_id, fact_key);

-- Semantic Long-Term Memories (Unstructured Facts)
CREATE TABLE semantic_memories (
    memory_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    source_message_id VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_semantic_memories_embedding ON semantic_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

---

### 2.4 Notes & Reminders

```sql
-- User Notes
CREATE TABLE notes (
    note_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notes_user ON notes(user_id, is_deleted, updated_at DESC);

-- Scheduled Reminders
CREATE TABLE reminders (
    reminder_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    due_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(32) DEFAULT 'PENDING', -- 'PENDING', 'DELIVERED', 'COMPLETED', 'CANCELLED'
    recurrence_rule VARCHAR(128), -- RRULE specification (e.g. 'FREQ=WEEKLY;BYDAY=TU,TH')
    delivery_channel VARCHAR(64) DEFAULT 'CLI', -- 'CLI', 'PUSH', 'WEB'
    delivered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reminders_due ON reminders(user_id, status, due_date ASC);
```

---

### 2.5 Execution State, Step Ledger & Action Approvals

```sql
-- Durable Execution Machine Turns
CREATE TABLE executions (
    execution_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    execution_mode VARCHAR(32) NOT NULL, -- 'FAST_PATH', 'DELIBERATE_PATH'
    status VARCHAR(32) NOT NULL, -- 'RUNNING', 'AWAITING_APPROVAL', 'COMPLETED', 'FAILED'
    active_plan JSONB,
    final_answer TEXT,
    total_tokens INTEGER DEFAULT 0,
    total_duration_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Discrete Execution Steps Ledger (Audit trail & checkpoint resumption)
CREATE TABLE execution_steps (
    step_id VARCHAR(64) PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL REFERENCES executions(execution_id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    tool_name VARCHAR(128),
    tool_arguments JSONB,
    tool_result JSONB,
    status VARCHAR(32) NOT NULL, -- 'SUCCESS', 'FAILED', 'AWAITING_APPROVAL'
    duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_execution_steps ON execution_steps(execution_id, step_number ASC);

-- Cryptographically Bound Action Approval Intents
CREATE TABLE action_approvals (
    action_id VARCHAR(64) PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL REFERENCES executions(execution_id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    tool_name VARCHAR(128) NOT NULL,
    arguments_payload JSONB NOT NULL,
    arguments_hash VARCHAR(64) NOT NULL, -- SHA-256 of canonical arguments
    approval_token VARCHAR(128) NOT NULL UNIQUE, -- HMAC signature
    status VARCHAR(32) DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED', 'EXPIRED'
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    decided_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_approvals_token ON action_approvals(approval_token, status);
```
