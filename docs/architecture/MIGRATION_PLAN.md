# V2 Migration Plan & Stage-by-Stage Implementation Roadmap

**Author:** Principal AI Systems Architect & Core Platform Team  
**Date:** October 2026  
**Status:** Approved Roadmap  
**Target Architecture:** `V2_TARGET_ARCHITECTURE.md`, `V2_COMPONENT_CONTRACTS.md`, `V2_DATA_MODEL.md`

---

## 1. Migration Principles & Safety Invariants

1. **Zero Downtime / Zero Regressions:** Existing functionality, tools, and integration tests must remain executable during migration.
2. **Strangler Fig Pattern:** Incrementally build the V2 architecture alongside the existing codebase, routing capabilities over as they achieve parity and verification in `benchmarks/v2/`.
3. **Strict Gate Criteria:** No stage proceeds to the next without automated unit and integration tests validating all component contracts.
4. **Data Preservation:** User documents in `documents/`, notes, and memory are migrated forward through deterministic data migration scripts.

---

## 2. Staged Migration Roadmap

```text
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 0: Audit & Baseline Measurement [COMPLETE]                       │
│ - Forensic audit of all modules in docs/architecture/PHASE_0_AUDIT.md  │
│ - 50-task deterministic benchmark harness in benchmarks/v2/            │
│ - Baseline report establishing V1 pass rate and defect count           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: Foundation & Data Infrastructure                              │
│ - Implement ExecutionContext threading across modules                  │
│ - Implement relational schema & SQLite/pgvector migrations             │
│ - Implement decoupled, non-mutating Observability EventSink            │
│ - Centralize Secret Vault & Configuration Settings                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: Tool Gateway, Safety & Capability Contracts                   │
│ - Replace mcp_layer/registry.py with typed Tool Gateway                │
│ - Implement ToolManifest with explicit capability declarations         │
│ - Implement HMAC Action Approval Token Engine                          │
│ - Harden Filesystem jail (per-user) and Web Fetch client (SSRF-safe)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: Knowledge Repository & Unified Retrieval Pipeline             │
│ - Implement KnowledgeRepository with relational facts & vectors        │
│ - Implement structured citation provenance pipeline (Chunk -> Quote)   │
│ - Implement bounded ContextBuilder with deterministic token budgeting  │
│ - Migrate existing documents and memories into relational schema       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: Dual-Path Orchestrator & Execution Engine                     │
│ - Implement Fast-Path router for single-turn Q&A and schedule lookups   │
│ - Implement Deliberate-Path state machine with LangGraph checkpointer  │
│ - Implement Outcome Verifier (replacing regex Goal Guard)              │
│ - Deprecate monolithic 1050-line planner_node.py                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: Presentation Layer, Verification & Final Cutover              │
│ - Implement unified CLI & REST API interfaces                          │
│ - Execute V2 Benchmark Harness across all 50 tasks                     │
│ - Verify 0 state corruption events, 0 approval bypasses, >95% success  │
│ - Final cutover and deprecation of legacy files                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stage Details & Acceptance Gates

### Stage 1: Foundation & Data Infrastructure
- **Deliverables:**
  - `app/core/context.py`: `ExecutionContext` immutable dataclass.
  - `app/core/config.py`: Pydantic `Settings` model reading `.env` with validation.
  - `app/storage/database.py`: SQLAlchemy / SQLite connection pool with schema DDL.
  - `app/observability/sink.py`: Decoupled `IObservabilitySink` that writes to JSONL / OpenTelemetry without touching graph state.
- **Acceptance Gate:**
  - Automated tests verify `ExecutionContext` propagates cleanly.
  - Database initialization passes schema migrations on SQLite.
  - Benchmark trace duplication check reports 0 duplicate events.

### Stage 2: Tool Gateway, Safety & Capability Contracts
- **Deliverables:**
  - `app/gateway/manifest.py`: `ToolManifest` schema with `SideEffectLevel` and `ApprovalRequirement`.
  - `app/gateway/dispatcher.py`: Validated tool invoker returning `ToolResultEnvelope`.
  - `app/gateway/approval.py`: HMAC-SHA256 `ApprovalTokenEngine` with token creation and verification.
  - `app/tools/filesystem.py`: Per-user isolated sandbox jail.
  - `app/tools/fetch.py`: SSRF-safe HTTP client with IP blacklisting.
- **Acceptance Gate:**
  - Unit tests verify destructive actions generate approval tokens and refuse execution without valid token.
  - Path traversal and private IP probes (`169.254.169.254`, `127.0.0.1`) are blocked with 100% interception rate.

### Stage 3: Knowledge Repository & Unified Retrieval Pipeline
- **Deliverables:**
  - `app/knowledge/repository.py`: CRUD for documents, chunks, profile facts, and notes.
  - `app/knowledge/retriever.py`: Hybrid dense + lexical search returning `CitationRecord` objects.
  - `app/knowledge/context_builder.py`: Token-bounded context assembly ($B \le 3,500$ tokens).
  - `scripts/migrate_v1_data.py`: Script migrating `memory.json`, `notes.json`, and documents to SQLite.
- **Acceptance Gate:**
  - Benchmark Category 1 (`doc_qa`) achieves $>90\%$ citation precision and recall.
  - Context size never exceeds 3,500 tokens regardless of retrieved document length.

### Stage 4: Dual-Path Orchestrator & Execution Engine
- **Deliverables:**
  - `app/orchestration/router.py`: Intent classifier producing `IntentClassification`.
  - `app/orchestration/fast_path.py`: Direct retrieval $\rightarrow$ synthesis loop.
  - `app/orchestration/deliberate_path.py`: Plan-Execute-Verify state machine with durable checkpointer.
  - `app/orchestration/verifier.py`: Semantic Outcome Verifier.
- **Acceptance Gate:**
  - Fast-path queries complete with $P50 < 1,500\text{ ms}$.
  - Approval flow pauses and resumes seamlessly via `Command(resume=...)` without rerunning from scratch.

### Stage 5: Presentation Layer, Verification & Final Cutover
- **Deliverables:**
  - `app/cli.py`: Interactive and one-shot terminal shell.
  - `app/api/`: FastAPI endpoints for `Chat`, `Today`, `My Knowledge`, `Reminders`, `Settings`.
  - `benchmarks/v2/runner.py`: Execution of full benchmark suite.
- **Acceptance Gate:**
  - Overall Benchmark Pass Rate $> 95\%$.
  - Approval Bypass Incidents: **0**.
  - State Corruption Events: **0**.
  - Legacy files (`nodes/planner_node.py`, `mcp_layer/registry.py`) safely decommissioned.
