# V2 Target Architecture: Personal Knowledge & Planning Assistant

**Author:** Principal AI Systems Architect & Core Platform Team  
**Date:** October 2026  
**Status:** Approved Specification  
**Supersedes:** `docs/architecture.md` (V1 Prototype)

---

## 1. System Vision & Product Boundaries

### 1.1 Product Promise
The **Personal Knowledge & Planning Assistant** connects a user's uploaded documents and personal notes with their schedule, interprets upcoming commitments, generates daily briefings, and executes safe tasks behind deterministic human approval gates.

### 1.2 Non-Negotiable Architectural Principles
1. **Modular Monolith First:** Clear boundaries and explicit dependency graphs within a single, highly maintainable deployment unit. No premature microservices or distributed RPC overhead.
2. **Explicit Execution Identity:** Every request, retrieval, tool execution, and log event threads `(user_id, session_id, execution_id, plan_id, step_id)`. Single-tenant globals are strictly forbidden.
3. **Durable State & Safe Resumption:** Human-in-the-loop (HITL) approval operates via durable workflow checkpoints and cryptographically bound approval action tokens. Rerunning entire graphs with global boolean flags (`user_confirmed: True`) is eliminated.
4. **Deterministic Tool Gateway:** Tools declare typed schemas, capability classifications, side-effect attributes, and idempotency guarantees. Zero policy guessing via substring matching.
5. **Dual-Path Orchestration:**
   - **Fast-Path:** Simple informational queries execute direct retrieval and synthesis in a single bounded LLM turn ($< 1,200\text{ ms}$).
   - **Deliberate-Path:** Multi-step commitments use a Plan-Execute-Verify loop with strict execution budgets and semantic outcome verification.
6. **Unified Knowledge Store:** Documents, notes, profile facts, and memories live in a structured schema with relational metadata and vector embeddings with verified citation provenance.
7. **Observability Without Mutation:** Execution traces are emitted through an isolated event sink. Node state does not accumulate or mutate trace arrays in-place.

---

## 2. Target Layered System Topology

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION & API LAYER                         │
│   CLI Interface  │  REST API (FastAPI)  │  Streaming WebSocket         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Request / ExecutionContext
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      APPLICATION & ORCHESTRATION                        │
│   Intent Classifier  │  Dual-Path Router  │  Execution State Machine   │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ Fast-Path: Context Builder ──► Synthesizer                      │   │
│   │ Deliberate-Path: Planner ──► Step Runner ──► Outcome Verifier   │   │
│   └────────────────────────────────────────────────────────────────┘   │
└───────────────────────┬───────────────────────────────┬────────────────┘
                        │                               │
        Read Operations │               Side-Effects &  │ Approval Token
                        ▼               Tool Execution  ▼
┌───────────────────────────────┐       ┌────────────────────────────────┐
│      DOMAIN CAPABILITIES      │       │     TOOL GATEWAY & SAFETY      │
│ - Knowledge Repository        │       │ - Policy Engine & Permissions  │
│ - Schedule & Calendar Service │       │ - Approval Token Verifier      │
│ - Reminders Lifecycle Manager │       │ - Structured Tool Dispatcher   │
│ - Daily Briefing Engine       │       │ - Tenant Sandbox Isolator      │
└───────────────┬───────────────┘       └───────────────┬────────────────┘
                │                                       │
                ▼                                       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     INTEGRATION & GATEWAY ADAPTERS                     │
│  SQLite/Postgres  │  Google Calendar API  │  Stdio MCP Subprocesses     │
│  pgvector Store   │  Local File Jails     │  SSRF-Guarded HTTP Client  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   INFRASTRUCTURE & FOUNDATION LAYER                    │
│   Storage Engine  │  Secret Vault  │  Event Bus & Trace Storage        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Specifications

### 3.1 Execution Identity & Context Flow
Every invocation instantiates an immutable context payload:
```python
@dataclass(frozen=True)
class ExecutionContext:
    user_id: str             # Tenant identity (e.g. "usr_alex_01")
    session_id: str          # Thread / Conversation ID (e.g. "ses_8823")
    execution_id: str        # Specific turn run ID (e.g. "exec_4910")
    plan_id: Optional[str]   # Active plan ID for deliberate executions
    step_id: Optional[str]   # Specific step identifier
    correlation_id: str      # Distributed trace correlation ID
```
Context is explicitly propagated into all repository queries, tool executions, and event emissions. Cross-tenant leakage is architecturally impossible.

### 3.2 Dual-Path Orchestration
```text
                     User Input
                         │
                         ▼
             Intent Classifier (Typed)
                         │
        ┌────────────────┴────────────────┐
        │                                 │
  [Simple Info]                     [Multi-Step Action]
        ▼                                 ▼
   Fast-Path                        Deliberate-Path
   - Retrieve Knowledge             - Generate Formal Plan
   - Assemble Bounded Prompt        - Checkpoint Approval Gates
   - Direct LLM Synthesis           - Execute Step via Tool Gateway
   - Format Citations               - Verify Outcome via Verifier
```

#### Fast-Path:
- Handles document Q&A, profile queries, schedule lookups, and conversational turns.
- Single LLM call. Target latency: $< 1,500\text{ ms}$.
- Context builder enforces strict token caps (see Section 3.4).

#### Deliberate-Path:
- Handles goal-oriented workflows requiring multiple steps, side-effects, or cross-source data transformations.
- Uses LangGraph checkpointer for durable state persistence across turn boundaries.
- Executes steps sequentially with explicit dependency passing.
- Outcome Verifier verifies that step outputs satisfy the user's criteria before returning `final`.

### 3.3 Durable Human Approval & Resumption Architecture
When a step requires human confirmation (e.g., deleting a note, modifying reminders, or altering records):
1. **Creation of Action Intent:** The Tool Gateway intercepts the request, blocks execution, generates a cryptographically bound `ActionIntent`:
   $$\text{Token} = \text{HMAC-SHA256}(\text{action\_id} \,\|\, \text{user\_id} \,\|\, \text{args\_hash} \,\|\, \text{expires\_at}, \text{Secret})$$
2. **Workflow Checkpoint:** The graph saves state to the durable checkpointer with `execution_status = "awaiting_approval"` and pauses without continuing or finishing.
3. **Resumption:**
   - When the user sends an approval decision, the API calls `graph.invoke(Command(resume=decision), config={"configurable": {"thread_id": session_id}})`.
   - The Gateway validates that the approval token matches the pending action intent, checks expiration, and executes the exact stored arguments.
   - The graph does NOT rerun from the beginning and does NOT use blanket booleans.

### 3.4 Bounded Context Assembly & Citation Architecture
Prompt context is assembled under a deterministic token budget ($B_{\text{total}} \le 3,500$ tokens):
- **Temporal Clock:** 100 tokens max (`date`, `day`, `timezone`).
- **User Profile & Preferences:** 400 tokens max (structured YAML/JSON).
- **Calendar & Schedule:** 500 tokens max (upcoming commitments within time window).
- **Retrieved Knowledge Chunks:** 2,500 tokens max (deduplicated, sorted by Cross-Encoder score).

#### Structured Citation Provenance:
Every retrieved passage carries an explicit chunk descriptor:
```json
{
  "citation_id": "cite_01",
  "document_id": "doc_travel_policy",
  "document_name": "travel_policy.txt",
  "chunk_id": "chunk_004",
  "page_number": 1,
  "char_start": 340,
  "char_end": 580,
  "exact_quote": "Hotel bookings are capped at $250 per night."
}
```
The final answer synthesizer is prompted to ground assertions using `[^cite_01]` tags, and the response envelope returns both the answer text and the array of verified citation records.

### 3.5 Deterministic Tool Gateway
The Tool Gateway replaces `mcp_layer/registry.py` and ad-hoc sanitizers with strict contract enforcement:
- **Capability Manifest:** Every tool specifies:
  - `name`: fully qualified string (`calendar.list_events`)
  - `description`: markdown documentation
  - `input_schema`: JSON Schema validated with Pydantic
  - `side_effect`: `NONE` (read-only), `REVERSIBLE_WRITE`, `IRREVERSIBLE_WRITE`, `DESTRUCTIVE`
  - `idempotent`: boolean
  - `approval_policy`: `NEVER`, `ALWAYS`, `CONDITIONAL`
- **Zero Substring Policy Guessing:** Destructive tools are explicitly labeled in their manifest, never inferred from word matching (`delete`, `drop`).
- **Structured Error Envelope:** Tools return typed payloads:
  ```json
  {
    "status": "success | error",
    "data": { ... },
    "error": {
      "code": "RESOURCE_NOT_FOUND",
      "message": "Note note_101 does not exist",
      "retryable": false
    }
  }
  ```

### 3.6 Tenant-Isolated Sandboxing & SSRF Guards
- **Filesystem Isolation:** Filesystem operations are strictly rooted to `storage/sandboxes/{user_id}/`. Windows device paths (`CON`, `NUL`), symlinks, and directory traversals (`../`) are intercepted before OS system calls.
- **SSRF Hardening:** Web fetching uses a custom socket connector:
  - Resolves domain to IP via DNS before socket connection.
  - Rejects connection if IP belongs to private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), or link-local (`169.254.0.0/16`).
  - Disables automatic HTTP 30x redirection.

### 3.7 Decoupled Observability Architecture
- State no longer contains `trace_events: Annotated[list, _merge_lists]`.
- Nodes emit events to an asynchronous, thread-safe `EventSink` / OpenTelemetry span exporter.
- State contains only lightweight correlation identifiers: `trace_id` and `correlation_id`.
- List duplication bugs and exponential state bloating are eliminated.
