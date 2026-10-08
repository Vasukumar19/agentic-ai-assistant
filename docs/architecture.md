# Agentic AI Assistant — Production Architecture Specification

## 1. System Overview

The **Agentic AI Assistant** is an enterprise-grade agentic system designed for local-first edge execution using open-weights models (`Qwen3:8b` via Ollama) with seamless cloud failover/upgrades (Claude, GPT-4o, Gemini, Groq).

It unifies:
1. **LangGraph StateGraph** reactive reasoning loop.
2. **Hybrid RAG Pipeline** (Dense FAISS + Sparse BM25 + Reciprocal Rank Fusion + Cross-Encoder Reranking).
3. **Long-Term Memory & User Profiling** (Declarative facts + semantic retrieval).
4. **Model Context Protocol (MCP)** multi-server tool abstraction across 7 servers.
5. **Deterministic Safety Guards** (Goal fulfillment verification, human-in-the-loop confirmation, sandbox boundary isolation).

---

## 2. Complete Architecture Topology

```text
User
  │
  ▼
Request
  │
  ▼
Intent Router
  ├── Chat Flow
  ├── Memory Extraction
  └── Task / Search Flow
             │
             ▼
   ┌──────────────────────┐
   │ Knowledge Retrieval  │
   │ - User Profile       │
   │ - Hybrid RAG         │
   │ - Dense Search       │
   │ - Keyword Search     │
   │ - Rank Fusion        │
   │ - Re-ranking         │
   └──────────┬───────────┘
              │
              ▼
       Context Builder
              │
              ▼
         Planner / Agent
              │
       ┌──────┼────────┐
       │      │        │
       ▼      ▼        ▼
   Local LLM  Model Router  Cloud LLM
              │
              ▼
      Action Needed?
          ├── No → Final Answer
          └── Yes → MCP Tools
                       │
          ┌────────────┼──────────────────────┐
          │            │                      │
          ▼            ▼                      ▼
      Calendar    Notes     Reminders   Filesystem
          │
          ├── GitHub
          ├── SQLite
          └── Web Fetch
```
        Tools --> DB[SQLite]
        Tools --> Web[Web Fetch]
    end
```

---

## 3. Core Subsystems

### A. State Management (`state.py`)
All execution state is centralized in `AgentState`:
- `question`, `route`, `answer`
- `completed_steps`, `current_step`, `tool_results`, `execution_status`
- `required_operations`, `completed_operations`, `remaining_operations`
- `retrieval_plan`, `retrieved_docs`, `profile_context`
- `trace_events`, `latency_breakdown`, `llm_usage`

### B. Hybrid RAG Subsystem
- **Dense Vector Search**: FAISS vector index using `sentence-transformers/all-MiniLM-L6-v2`.
- **Sparse Lexical Search**: BM25 keyword index over tokenized chunks.
- **Reciprocal Rank Fusion (RRF)**: Merges dense and sparse ranks with \(k=60\) constant.
- **Cross-Encoder Reranking**: `ms-marco-MiniLM-L-6-v2` computes query-document cross-attention relevance scores.

### C. Multi-LLM Layer (`llm.py`)
Unified `get_llm()` factory with plug-and-play provider switching:
- `ollama`: $0 local offline inference (`qwen3:8b`, `llama3`).
- `anthropic`: `claude-3-5-sonnet-20241022`.
- `openai`: `gpt-4o`.
- `google`: `gemini-1.5-pro` / `gemini-2.0-flash`.
- `groq`: Ultra-fast inference with `llama-3.3-70b-versatile`.

### D. Model Context Protocol (MCP) Registry (`mcp_layer/`)
- Unified dynamic discovery and dispatch for 7 MCP stdio servers.
- Parameter auto-healing and JSON schema validation.
- Sandboxed execution with subprocess crash protection.

### E. Deterministic Safety & Policy Engine
1. **Human-in-the-Loop Confirmation**: Destructive operations (`delete_*`, `drop_table`) strictly require human confirmation before execution, pausing the graph in `awaiting_confirmation` status until confirmed.
2. **Transactional Soft-Delete & Undo Staging**: Deletions in SQLite are staged to shadow tables (`_deleted_records`), and Notes/Reminders deletions are staged to `_trash` dictionaries, enabling instant `undo_delete`.
3. **Deterministic Goal Fulfillment Guard**: `planning/goal_guard.py` enforces completion of all abstract sub-tasks before allowing the planner to transition to `final`.
4. **Filesystem Sandboxing**: All file I/O is restricted to `mcp_sandbox/` with path-traversal prevention (`../`).
5. **Loop Detection & Execution Budgets**: State-aware call-signature hashing catches cyclic oscillations with a 10-step hard execution budget.
6. **Structured Tracing**: JSONL execution traces persisted in `traces/` with latency metrics.

