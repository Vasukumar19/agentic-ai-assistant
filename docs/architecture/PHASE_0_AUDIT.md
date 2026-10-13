# Phase 0 Architecture Audit: Agentic AI Assistant

**Author:** Principal AI Systems Architect & Reliability Engineering  
**Date:** October 2026  
**Status:** Complete Initial Audit  
**Target:** Architecture Modernization & Production Migration (V2)

---

## 1. Executive Summary & Audit Methodology

### 1.1 Context & Objectives
The **Agentic AI Assistant** is an experimental agentic system engineered on top of LangGraph, Ollama (`qwen3:8b`), local Model Context Protocol (MCP) servers, and hybrid retrieval (FAISS dense vector search + BM25 sparse keyword search + Reciprocal Rank Fusion + Cross-Encoder reranking).

While the system successfully demonstrates advanced capabilities in controlled test cases (such as multi-hop reasoning, local tool execution, and basic sandboxing), an exhaustive architectural inspection reveals that the codebase suffers from severe architectural fragility, concurrency hazards, security vulnerabilities, prompt bloat, and missing abstraction boundaries. 

The purpose of this Phase 0 audit is to provide a forensic, file-by-file inspection of every component in the repository, document the architectural root causes of its failure modes, evaluate compliance against documentation, and establish a clear plan for what to keep, refactor, replace, or eliminate.

### 1.2 System Scope Definition
The target product is defined as a **Personal Knowledge & Planning Assistant** for students, researchers, and knowledge workers with the core promise:
> *"Connect your personal knowledge with your schedule, understand what matters, and help you prepare for what's coming."*

Initial scope is strictly bounded to:
1. Ingesting documents and retrieving passages with verifiable citations.
2. Saving, retrieving, updating, and resolving personal knowledge.
3. Read-only Google Calendar synchronization and schedule interpretation.
4. Synthesizing cross-source daily briefings and commitment preparation.
5. Reliable reminder scheduling and lifecycle tracking.
6. Safe execution of external side-effects behind deterministic authorization gates.

Out of scope for this phase:
- Unrestricted autonomous browser scraping, WhatsApp/voice interfaces, arbitrary banking/shopping integrations, write operations directly into Google Calendar (until approval safety is verified), and monolithic email sending bypasses.

---

## 2. Comprehensive Module-by-Module Audit

| Module Path | Primary Responsibility | Dependencies | Inputs / Outputs | State Mutated | Persistence Mechanism | Security Risk | Test Coverage | Recommended Action |
|---|---|---|---|---|---|:---:|:---:|:---:|
| `main.py` | Interactive CLI & one-turn runner | `graph`, `state`, `config`, `llm`, `mcp_layer.registry` | User text string $\rightarrow$ Terminal stdout | In-memory `last_pending_state`, `last_query` | None (delegates to graph) | High (TOCTOU on re-run) | Manual smoke | **Rewrite** (replace with robust CLI / API entrypoint) |
| `graph.py` | LangGraph StateGraph topology & compilation | `langgraph`, `state`, all nodes | Input dict $\rightarrow$ AgentState dict | In-memory LangGraph state | Flat file `memory/chat_history.json` | Low | Integration & E2E | **Refactor** (restructure nodes, clean fan-outs, isolate checkpointing) |
| `state.py` | Graph state definition & reducers | `typing`, `langchain_core`, `langgraph` | State updates $\rightarrow$ Merged state | In-memory TypedDict | LangGraph internal checkpointer | High (duplicate trace list) | Implicit in all | **Rewrite** (introduce typed execution identities, fix reducers) |
| `config.py` | System-wide paths, constants & env vars | `pathlib`, `os`, `dotenv` | Environment variables $\rightarrow$ Typed constants | Process env | None | Medium (scattered secrets) | Unit/E2E | **Modify** (centralize config, validate schema with Pydantic) |
| `llm.py` | Multi-provider LLM factory | `langchain_community`, `langchain_*` | Provider/model name $\rightarrow$ BaseChatModel | In-memory model instance | None | Low | Basic | **Keep & Refine** (add timeout, structured fallbacks) |
| `ingest.py` | Document ingestion & indexing | `langchain`, `faiss`, `pickle` | Raw `.txt` documents $\rightarrow$ FAISS index & BM25 pickle | Disk files | `faiss_index/`, `bm25_chunks.pkl` | Low | Indirect | **Refactor** (replace pickle with robust store, improve chunking) |
| `reranker.py` | Cross-encoder passage reranking | `sentence_transformers` | Query + candidate passages $\rightarrow$ Reranked items | Model memory cache | In-memory model weights | Low | Indirect | **Keep** (optimize cold start, add batching) |
| `nodes/router.py` | Intent classification | `llm`, heuristics | Question $\rightarrow$ `route` | In-memory state | None | Medium (route evasion) | Golden & Adv | **Refactor** (support composite intents, eliminate brittle string matches) |
| `nodes/chat.py` | Casual conversation responses | `llm` | User message $\rightarrow$ String answer | In-memory state | None | Low | Golden | **Keep** |
| `nodes/memory_extractor.py` | Profile & semantic memory extraction & storage | `llm`, `faiss`, `embeddings` | Message $\rightarrow$ Profile dict & semantic text | Disk files | `memory/memory.json`, `memory/semantic_memory/` | Medium (unlocked concurrent writes) | Golden & Adv | **Rewrite** (migrate to transactional relational / vector storage) |
| `nodes/memory_retriever.py` | Profile & semantic memory retrieval | `faiss`, `embeddings` | Query $\rightarrow$ Profile context, semantic context | In-memory state | None | Low | Golden & Adv | **Refactor** (unify memory retrieval contracts) |
| `nodes/retrieval_planner.py` | Decides which retrieval sources to consult | `llm` | Query $\rightarrow$ `retrieval_plan` dict | In-memory state | None | Low | Golden | **Modify** (add schema validation) |
| `nodes/rag_retriever.py` | Hybrid RAG search (FAISS + BM25 + RRF + Reranker) | `faiss`, `bm25`, `rrf`, `reranker` | Query $\rightarrow$ Retrieved chunks & context | In-memory state | Reads `faiss_index/`, `bm25_chunks.pkl` | Low | Golden & Adv | **Refactor** (strict citation metadata tracking, passage limits) |
| `nodes/embeddings.py` | SentenceTransformer embedding singleton | `langchain_community` | Text $\rightarrow$ Float vector | In-memory cache | None | Low | Direct | **Keep** |
| `nodes/bm25.py` | Lexical search over tokenized chunks | `rank_bm25`, `pickle` | Query $\rightarrow$ Ranked doc chunks | In-memory index | Reads `bm25_chunks.pkl` | Low | Direct | **Keep** |
| `nodes/rrf.py` | Reciprocal Rank Fusion calculation | None | Rank lists $\rightarrow$ Fused rank list | In-memory | None | Low | Direct | **Keep** |
| `nodes/context_builder.py` | Prompt context assembly | None | Retrieved texts $\rightarrow$ Combined context string | In-memory state | None | Medium (context overflow) | Golden | **Modify** (enforce token budget & passage deduplication) |
| `nodes/planner_node.py` | ReAct reasoning, DAG planner, heuristics | `llm`, `mcp_layer`, `pydantic` | State + context $\rightarrow$ Tool calls or final answer | In-memory state | None | High (argument guessing, hardcoded bypasses) | Golden & E2E | **Rewrite** (split monolithic planner into clean planner + verifier) |
| `nodes/tools.py` | Tool dispatch, tracing, safety gates | `mcp_layer.registry`, `langchain` | Tool call $\rightarrow$ Tool result string | In-memory state, disk sandbox | External servers, `mcp_sandbox/` | High (blocking interactive stdin, weak gate) | Security & Integration | **Rewrite** (replace with isolated Tool Gateway & Approval Engine) |
| `mcp_layer/registry.py` | Tool registration & policy inference | `mcp_layer.client`, `pydantic` | Server configs $\rightarrow$ Dynamic tools | In-memory registry | None | High (keyword policy matching) | Security & Integration | **Rewrite** (explicit declared tool capability contracts) |
| `mcp_layer/client.py` | Subprocess stdio MCP client | `mcp.client.stdio` | Tool name + arguments $\rightarrow$ MCP JSON result | Child processes | External MCP server process | Low | Integration | **Keep & Harden** (process lifecycle management, pipe health) |
| `mcp_layer/adapter.py` | MCP tool to LangChain StructuredTool | `langchain_core` | MCP tool spec $\rightarrow$ StructuredTool | In-memory | None | Low | Integration | **Keep** |
| `mcp_layer/discovery.py` | Dynamic MCP server discovery | `mcp_layer.registry` | Configs $\rightarrow$ Registered tools | In-memory registry | None | Low | Integration | **Keep** |
| `mcp_layer/models.py` | Pydantic data schemas for MCP | `pydantic` | Data dicts $\rightarrow$ Validated objects | In-memory | None | Low | Integration | **Keep & Extend** |
| `mcp_layer/errors.py` | MCP error types | None | Exceptions | None | None | Low | Unit | **Keep** |
| `planning/goal_guard.py` | Operational goal verification | `re` | Query + tool results $\rightarrow$ Fulfillment status | In-memory state | None | Medium (regex verb false-positives) | Golden | **Modify / Replace** (semantic state verification) |
| `planning/classifier.py` | Complexity classifier for planning depth | `re` | Query $\rightarrow$ Classification string | In-memory state | None | Low | Golden | **Modify** |
| `planning/schema.py` | Pydantic models for DAG Plan & Steps | `pydantic` | Plan dict $\rightarrow$ Typed Plan object | In-memory | None | Low | Unit | **Keep** |
| `planning/validation.py` | Plan validation rules | None | Plan $\rightarrow$ Validation result | In-memory | None | Low | Unit | **Keep** |
| `observability/trace.py` | Structured JSONL trace event helpers | `dataclasses`, `time` | Event attributes $\rightarrow$ TraceEvent dict | Mutates `state["trace_events"]` | In-memory list (and disk via storage) | High (state duplication bug) | Unit & E2E | **Rewrite** (eliminate in-place mutation, decouple from state reducer) |
| `observability/storage.py` | JSONL trace file persistence | `json`, `pathlib` | Trace events $\rightarrow$ `traces/<id>.jsonl` | Disk files | `traces/` directory | Low | Unit | **Keep** |
| `observability/errors.py` | Error taxonomy and error payloads | `enum` | Exception $\rightarrow$ Error payload dict | None | None | Low | Unit | **Keep** |
| `observability/ids.py` | Unique ID generators (`req_`, `tr_`) | `uuid`, `time` | State $\rightarrow$ Populated IDs | In-memory state | None | Low | Unit | **Keep** |
| `observability/redaction.py` | Secret redaction & result summarization | `re` | Strings/dicts $\rightarrow$ Redacted data | None | None | Low | Security | **Keep** |
| `observability/retry.py` | Exponential backoff retry helper | `time` | Callable $\rightarrow$ Result | None | None | Low | Chaos | **Keep** |
| `observability/timeout.py` | Thread-based execution timeout | `concurrent.futures` | Callable + timeout_s $\rightarrow$ Result | Threads | None | Low | Chaos | **Keep** |
| `mcp_calendar_server.py` | Local mock calendar MCP server | `mcp`, `json` | Stdio requests $\rightarrow$ JSON responses | Disk file | `mcp_data/calendar.json` | Medium (schema divergence) | Integration | **Deprecate / Unify** (align schema with Google Calendar contract) |
| `google_calendar_server.py` | Real Google Calendar OAuth MCP server | `googleapiclient`, `mcp` | Stdio requests $\rightarrow$ Google API calls | Google Cloud API | Remote Google Calendar | Medium (scattered tokens) | Integration | **Refactor** (isolate to read-only adapter, token vault) |
| `gmail_server.py` | Real Gmail OAuth MCP server | `googleapiclient`, `mcp` | Stdio requests $\rightarrow$ Gmail API calls | Google Cloud API | Remote Gmail Inbox | High (unconfirmed email dispatch) | Integration | **Eliminate from initial V2 scope** (safety boundary) |
| `mcp_notes_server.py` | Local notes MCP server | `mcp`, `json` | Stdio requests $\rightarrow$ JSON responses | Disk file | `mcp_data/notes.json` | Low | Integration | **Migrate** (unify under personal knowledge repository) |
| `mcp_reminders_server.py` | Local reminders MCP server | `mcp`, `json` | Stdio requests $\rightarrow$ JSON responses | Disk file | `mcp_data/reminders.json` | Low | Integration | **Refactor** (introduce robust scheduling and delivery lifecycle) |
| `mcp_filesystem_server.py` | Sandboxed local file I/O MCP server | `mcp`, `pathlib` | Stdio requests $\rightarrow$ File contents | Disk files | `mcp_sandbox/` directory | High (shared unisolated sandbox) | Security | **Harden** (tenant/session isolation, path validation) |
| `mcp_github_server.py` | Local mock GitHub issues/repo server | `mcp`, `json` | Stdio requests $\rightarrow$ JSON responses | Disk file | `mcp_data/github_store.json` | Low | Integration | **Deprecate / Keep as mock** |
| `mcp_sqlite_server.py` | SQLite database query & mutation server | `mcp`, `sqlite3` | Stdio requests $\rightarrow$ SQLite rows | SQLite DB | `mcp_sandbox/app.db` | High (SQL injection in PRAGMA/keys) | Integration | **Harden** (parameterized statements, strict allowlist) |
| `mcp_fetch_server.py` | External HTTP GET/POST fetch server | `mcp`, `urllib.request` | Stdio requests $\rightarrow$ Web response text | Outbound HTTP sockets | None | Critical (SSRF, cloud metadata leak) | Security | **Harden** (private IP/DNS blocking, redirect validation) |

---

## 3. Forensic Investigation of the 19 Critical Architectural Flaws

### Issue 1: State Reducer Contradiction & Quadratic Trace Duplication
- **Location:** `observability/trace.py` (lines 82–86, 173–178) and `state.py` (lines 18–25, 115).
- **Observed Behavior:** In multi-step agent loops, the length of `state["trace_events"]` grows quadratically, leading to multi-megabyte states, serialization slowdowns, and corrupted JSONL log files.
- **Root Cause Analysis:**
  In `state.py`:
  ```python
  def _merge_lists(left: Optional[list], right: Optional[list]) -> list:
      if left is None: left = []
      if right is None: right = []
      return list(left) + list(right)

  class AgentState(TypedDict):
      ...
      trace_events: Annotated[Optional[list[dict]], _merge_lists]
  ```
  LangGraph invokes `_merge_lists(current_state_val, node_return_val)` whenever a node returns a dictionary containing `"trace_events"`.
  However, in `observability/trace.py`:
  ```python
  def append_event(state: dict, event: dict) -> None:
      if "trace_events" not in state or state["trace_events"] is None:
          state["trace_events"] = []
      state["trace_events"].append(event)
  ```
  The helper mutates `state["trace_events"]` directly in memory. When the node completes (see lines 174–177 of `observability/trace.py`):
  ```python
  result["trace_events"] = state.get("trace_events")
  return result
  ```
  The node returns the *entire accumulated list* back to LangGraph. LangGraph then invokes the reducer:
  `_merge_lists(state["trace_events"], result["trace_events"])`, which calculates:
  $$\text{events}_{\text{new}} = \text{events}_{\text{all}} + \text{events}_{\text{all}}$$
  If a graph runs 8 steps, step 1 has 1 event merged to 2, step 2 has 3 merged to 6, rapidly multiplying all previous events.
- **Architectural Remedy:**
  Nodes must NEVER return the entire event history. Either:
  1. Return ONLY the new events emitted in that specific step (`{"trace_events": [new_event]}`), letting the list reducer append them cleanly without mutation; or
  2. Decouple observability entirely from the conversational graph state and route events asynchronously through an event bus / logger to durable storage.

---

### Issue 2: Insecure Human Approval & Resumption Model
- **Location:** `main.py` (lines 130–145) and `nodes/tools.py` (lines 178–211).
- **Observed Behavior:** If an action requires confirmation, the assistant prints a prompt and terminates the current execution. When the user types `"yes"`, the entire graph runs from scratch, sending a blanket `user_confirmed: True` flag.
- **Root Cause Analysis:**
  ```python
  # main.py lines 133-134
  if user_input.lower() in ("yes", "y", "confirm", "proceed", "sure", "ok", "do it"):
      print("\n[CONFIRMED] Executing confirmed operation...")
      out = app.invoke({"question": last_query, "user_confirmed": True})
  ```
  This implementation suffers from three critical flaws:
  1. **Loss of Suspended Context:** It does not resume a suspended execution thread via LangGraph checkpointer `Command(resume=...)` or tokenized action.
  2. **Blanket Authorization:** Passing `user_confirmed: True` at the root state grants authorization to *every* tool invocation during that rerun, not just the specific action the user authorized.
  3. **Time-of-Check to Time-of-Use (TOCTOU) Flaw:** Because the graph is rerun from scratch against non-deterministic LLMs, the planner might select a different tool, different arguments, or re-execute prior side-effects that had already occurred before the prompt paused.
- **Architectural Remedy:**
  Implement a cryptographically bound Action Intent record containing `action_id`, `tool_name`, `exact_args_hash`, `user_id`, and `expires_at`. The workflow must remain paused at a durable checkpoint and only execute the specific approved action payload upon receipt of the approval signature.

---

### Issue 3: Silent Argument Guessing & Synthetic Rewriting
- **Location:** `nodes/planner_node.py` (`_sanitize_tool_call`, lines 126–170).
- **Observed Behavior:** When the LLM outputs missing or malformed tool arguments, the planner node silently rewrites them using arbitrary heuristics.
- **Root Cause Analysis:**
  Forensic examination of `_sanitize_tool_call` reveals:
  ```python
  # Line 132: Erases intent to get a specific event and lists everything instead
  if t in ("calendar.get_event", "calendar_get_event") and "event_id" not in args:
      t = "calendar.list_events"

  # Lines 150-152: Multiplies arbitrary numeric arguments together!
  num_vals = [str(v) for v in args.values() if isinstance(v, (int, float))]
  if len(num_vals) >= 2:
      args["expression"] = " * ".join(num_vals)

  # Lines 156-158: Regex extracts math from question and injects into calculator
  # Lines 167-168: Injects user question verbatim if search query is missing
  if ("query" not in args or not str(args.get("query", "")).strip()) and question:
      args["query"] = question
  ```
  This heuristic argument tampering causes catastrophic silent bugs:
  - If a tool requires two configuration numbers like `{"limit": 10, "offset": 50}`, the sanitizer transforms the calculator expression to `"10 * 50"` = `500`.
  - Erasing `calendar.get_event` and converting it to `calendar.list_events` masks model failure and causes unexpected data dumping.
- **Architectural Remedy:**
  Eliminate all heuristic argument guessing. If tool parameters fail schema validation, return a structured schema validation error back to the LLM so it can properly replan, or prompt the user for clarification.

---

### Issue 4: Monolithic Planner Bloat & Overlapping Planning Strategies
- **Location:** `nodes/planner_node.py` (1,050 lines).
- **Observed Behavior:** Extreme file bloat containing four distinct, overlapping, and competing control flows.
- **Root Cause Analysis:**
  The file simultaneously contains:
  1. A ReAct baseline planner prompt (`PLANNER_SYSTEM_PROMPT_TEMPLATE`, lines 1–125, 686–1050).
  2. A DAG dependency planner (`_dependency_planner`, lines 340–644) that generates a Pydantic `Plan`.
  3. A complexity classifier router (`_hybrid_route`, lines 646–684).
  4. Hardcoded domain bypasses for Gmail and Google Calendar (lines 403–414, 495–511).
  5. Ad-hoc tool sanitizers and output pruning logic.
  This creates maintenance paralysis: changes to tool schemas or prompts must be coordinated across multiple planning branches, and test failures are unpredictable because execution switches between dependency execution and ReAct baseline based on hidden state flags.
- **Architectural Remedy:**
  Replace the 1,050-line monolith with a clean, single-responsibility ReAct/Plan-and-Execute engine that interacts strictly through typed contracts and delegates output pruning and verification to dedicated components.

---

### Issue 5: Parallel Fan-Out Asymmetry & Reducer Clashing
- **Location:** `graph.py` (lines 229–241, 319–327).
- **Observed Behavior:** Race conditions and duplicated step execution during retrieval.
- **Root Cause Analysis:**
  In `graph.py`:
  ```python
  def fan_out_retrievers(state: dict):
      sends = []
      plan = state.get("retrieval_plan", {})
      if plan.get("profile") or plan.get("semantic"):
          sends.append(Send("memory_retriever", state))
      if plan.get("rag"):
          sends.append(Send("rag_retriever", state))
      if not sends:
          sends.append(Send("context_builder", state))
      return sends

  graph.add_conditional_edges("retrieval_planner", fan_out_retrievers,
      ["memory_retriever", "rag_retriever", "context_builder"])
  graph.add_edge("memory_retriever", "context_builder")
  graph.add_edge("rag_retriever", "context_builder")
  ```
  When both `memory_retriever` and `rag_retriever` execute in parallel, both route independently to `context_builder`. Depending on scheduling, `context_builder` may be invoked twice or receive concurrent state updates, triggering list and dict merger conflicts.
- **Architectural Remedy:**
  Use a deterministic fan-in barrier node or execute retrieval stages in an explicit, sequential orchestrator pipeline (`Retrieve Memory` $\rightarrow$ `Retrieve Documents` $\rightarrow$ `Build Context`).

---

### Issue 6: Flat-File Single-Tenant Storage & Race Conditions
- **Location:** `memory/memory.json`, `memory/chat_history.json`, `memory/semantic_memory/`.
- **Observed Behavior:** Concurrent requests clobber profile data; chat history is truncated to an arbitrary 100 entries without session partitioning.
- **Root Cause Analysis:**
  - `memory_saver_node` reads the entire `memory/memory.json` file, updates keys in-memory, and overwrites the file on disk without file locking (`flock`) or transactional consistency.
  - No `user_id` or `tenant_id` exists: all users share the same JSON file. If User A updates their name and User B writes their location, race conditions cause lost writes.
  - `memory/chat_history.json` caps history at `history[-100:]`, mingling all conversations across all time into one unindexed array.
- **Architectural Remedy:**
  Migrate personal knowledge and conversation state to a relational/document data model (SQLite/PostgreSQL with pgvector) keyed by `(user_id, session_id)` with transactional isolation.

---

### Issue 7: Substring-Based Policy Inference vs Declared Capability Contracts
- **Location:** `mcp_layer/registry.py` (`_infer_policy`, lines 30–36, 153).
- **Observed Behavior:** Tools are misclassified as safe or destructive based solely on substring matches in their names.
- **Root Cause Analysis:**
  ```python
  if any(x in low for x in ["delete", "remove", "destroy", "drop", "truncate", "purge", "clear", "wipe", "flush", "erase", "unlink"]):
      return {"operation": "destructive", "risk_level": "high", "requires_confirmation": True}
  if any(x in low for x in ["create", "write", "update", "send", "insert", "add", "post"]):
      return {"operation": "write", "risk_level": "medium", "requires_confirmation": False}
  return {"operation": "read", "risk_level": "low", "requires_confirmation": False}
  ```
  - Any destructive operation that does not use those exact words (e.g. `prune_history`, `execute_query`, `archive_all`, `override_config`) defaults to `operation: read`, `risk_level: low`, and executes without confirmation.
  - Safe tools with names containing substrings (e.g. `get_deleted_notes_summary`) are falsely flagged as destructive.
- **Architectural Remedy:**
  Require every tool definition to declare an explicit capability contract with typed attributes: `idempotent: bool`, `side_effect: SideEffectType`, `approval_required: bool`.

---

### Issue 8: Unvalidated SSRF & Open Redirect in Web Fetch Server
- **Location:** `mcp_fetch_server.py` (lines 23–85).
- **Observed Behavior:** The agent can be coerced into reading internal network endpoints, localhost ports, and cloud instance metadata.
- **Root Cause Analysis:**
  ```python
  if not url.startswith("http://") and not url.startswith("https://"):
      return f"Error: Invalid URL scheme: {url}"
  req = urllib.request.Request(url, headers={"User-Agent": "agentic-ai-mcp/1.0"})
  with urllib.request.urlopen(req, timeout=5.0) as resp:
      ...
  ```
  - The server does not resolve DNS or validate destination IP addresses against RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), or link-local cloud metadata endpoints (`169.254.169.254`).
  - `urllib.request.urlopen` automatically follows HTTP 301/302 redirects by default, allowing attackers to bypass domain checks via external redirectors.
- **Architectural Remedy:**
  Harden HTTP fetching using an SSRF-safe client that resolves IP addresses prior to connection, blocks private/reserved ranges, prohibits redirection to non-public addresses, and bounds payload downloads.

---

### Issue 9: Shared Sandbox Boundary & Path Traversal Risks
- **Location:** `mcp_filesystem_server.py` (lines 12, 28–30, 46–48).
- **Observed Behavior:** All users share a single `mcp_sandbox/` directory; Windows-specific device files and symlinks are unhandled.
- **Root Cause Analysis:**
  ```python
  target = (SANDBOX / path).resolve()
  target.relative_to(SANDBOX.resolve())
  ```
  While `relative_to` blocks basic `../` traversal, the design has major gaps:
  - No per-user or per-session scoping: every user can read and overwrite every other user's files.
  - Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) can cause filesystem hangs.
  - No quota enforcement, allowing files of unbounded count or size to fill disk space.
- **Architectural Remedy:**
  Implement per-user sandboxing (`mcp_sandbox/{user_id}/`) with strict canonical path normalization, quota management, and automatic TTL cleanup.

---

### Issue 10: SQL Injection & Unsafe Dynamic Statements in SQLite Server
- **Location:** `mcp_sqlite_server.py` (lines 92, 151, 179, 191, 239).
- **Observed Behavior:** Table names and column identifiers are directly interpolated into SQL strings.
- **Root Cause Analysis:**
  ```python
  cursor.execute(f"PRAGMA table_info({table_name})")
  cursor.execute(f"INSERT OR REPLACE INTO {table_name} ({cols}) VALUES ({placeholders})", values)
  cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
  cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
  ```
  - While values use `?` placeholders, `table_name` and `cols` (derived from JSON keys) are formatted directly with Python f-strings.
  - In `read_query`, only a shallow `not trimmed.lower().startswith("select")` check is performed. An attacker can execute CTE queries with mutations, call SQLite administrative functions, or execute stacked queries.
- **Architectural Remedy:**
  Validate all table and column names against a strict alphanumeric allowlist or database catalog before executing queries. Disallow multiple statements and use SQLite read-only connection flags (`URI mode ?mode=ro`).

---

### Issue 11: Schema Divergence & Fragmented Calendar Adapters
- **Location:** `mcp_calendar_server.py` vs `google_calendar_server.py`.
- **Observed Behavior:** Two parallel calendar implementations exist with conflicting schemas and tool names.
- **Root Cause Analysis:**
  - `mcp_calendar_server.py` provides `calendar.list_events`, expects parameter `date: str` (YYYY-MM-DD), and returns local event IDs (`evt_001`).
  - `google_calendar_server.py` provides `google_calendar.list_events`, expects `time_min`, `time_max`, `max_results`, and returns Google API event objects.
  - The planner must know which server is mounted and adapt its reasoning dynamically.
- **Architectural Remedy:**
  Define a single canonical `CalendarGateway` protocol with a unified event schema (`id`, `title`, `start_time`, `end_time`, `attendees`, `status`). Swap the backend (Local JSON vs Google Calendar) behind the gateway without exposing implementation differences to the planner.

---

### Issue 12: Scope Creep & Monolithic Gmail Coupling
- **Location:** `gmail_server.py` and `nodes/planner_node.py` (lines 403–414, 495–511).
- **Observed Behavior:** Unconfirmed email dispatch is hardcoded into the planner.
- **Root Cause Analysis:**
  - `gmail_server.py` exposes `send_message`, which is classified as `risk_level: medium` in `mcp_layer/registry.py` and does not require user confirmation.
  - `planner_node.py` contains hardcoded shortcuts that detect `"calendar"` and `"gmail"` in the query and automatically fabricate a hardcoded plan.
  - Initial product scope explicitly excludes email sending until read-only planning and reminders are stabilized.
- **Architectural Remedy:**
  Deactivate Gmail mutations from the active tool registry during Phase 1. Remove hardcoded special cases from the planner.

---

### Issue 13: Hybrid RAG Pipeline Bottlenecks & Missing Citations
- **Location:** `ingest.py`, `nodes/rag_retriever.py`, `reranker.py`.
- **Observed Behavior:** Ingestion uses insecure Python `pickle`; documents lack formal chunk-level citation anchors; reranker incurs heavy cold-start latency.
- **Root Cause Analysis:**
  - `bm25_chunks.pkl` relies on `pickle.dump` / `pickle.load`, which is an unauthenticated deserialization risk.
  - When passages are formatted into `rag_context`, citation identifiers are formatted as ad-hoc strings (`[Doc 1 | travel_policy.txt p.1]`), but there is no structured citation tracing mapping generated output sentences to source chunk IDs.
  - Ingestion lacks support for incremental updates: adding one document requires rebuilding the entire index.
- **Architectural Remedy:**
  Store chunks and lexical indices in SQLite/PostgreSQL. Implement structured citation extraction returning verified `(chunk_id, source_doc, page_number, exact_quote)` tuples with the final answer.

---

### Issue 14: Unbounded Context Injection & Context Window Overflow
- **Location:** `nodes/context_builder.py` (lines 20–46).
- **Observed Behavior:** Retrieved passages, profile memories, and semantic results are concatenated without length checks or token budgeting.
- **Root Cause Analysis:**
  ```python
  context_parts = [temporal_context]
  if profile_context: context_parts.append(profile_context)
  if semantic_context: context_parts.append(semantic_context)
  if rag_context: context_parts.append(rag_context)
  combined = "\n\n".join(context_parts)
  ```
  If RAG retrieves 10 long passages and semantic memory returns 15 entries, the combined context can exceed 10,000 tokens, degrading local model (`qwen3:8b`) reasoning performance and causing context truncation.
- **Architectural Remedy:**
  Implement strict token budgets for each context section (e.g. Temporal: 100 tokens, Profile: 400 tokens, Documents: 2,500 tokens) with priority-based truncation.

---

### Issue 15: Brittle Intent Classification on Composite & Adversarial Queries
- **Location:** `nodes/router.py` (lines 30–87, 184–210).
- **Observed Behavior:** Composite queries (e.g., `"Remember I like Python and what is on my calendar?"`) drop one intent; empty queries trigger LLM hallucinations.
- **Root Cause Analysis:**
  - `router.py` forces a single categorical route: `"chat" | "memory_update" | "research_query"`.
  - Prefix matching (`_is_greeting`, `_is_action_command`) eagerly routes to `research_query` if words like `"calculate"` appear anywhere in the text, completely ignoring personal memory facts in the same utterance.
  - Empty or whitespace input falls through to LLM classification, generating unpredictable output.
- **Architectural Remedy:**
  Implement a multi-label intent classifier or allow composite pipelines where memory extraction runs passively on all conversational turns before planning.

---

### Issue 16: Regex Verb Matching Vulnerabilities in Goal Guard
- **Location:** `planning/goal_guard.py` (lines 19–26, 65–91).
- **Observed Behavior:** Goal Guard falsely demands tool execution on informational queries and fails on compound queries.
- **Root Cause Analysis:**
  `extract_abstract_operations` uses naive keyword regexes:
  ```python
  OPERATION_PATTERNS = [
      ("calculate", re.compile(r"\b(calculate|compute|math|multiply|divide|add up|sum|percentage|% of...)\b")),
      ...
  ]
  ```
  If a user asks: *"Can you explain how to calculate compound interest?"*, the guard extracts `calculate` as an operation requirement and blocks the planner from returning `final` until the `calculator` tool is called.
- **Architectural Remedy:**
  Replace lexical regex verb matching with semantic plan verification based on the model's explicit sub-goal decomposition.

---

### Issue 17: Lack of Structured Error Recovery & Loop Cascade
- **Location:** `nodes/tools.py` (lines 127–132) and `nodes/planner_node.py`.
- **Observed Behavior:** Tool errors returned as raw strings cause the planner to repeat identical failing calls until the step budget is exhausted.
- **Root Cause Analysis:**
  When a tool fails, it returns a plain string: `f"Error running tool '{tool_name}': {e}"`. The planner receives this in the tool result history but often interprets the error string as normal text or tries calling the tool again with the same failing arguments.
- **Architectural Remedy:**
  Return typed tool execution envelopes:
  ```json
  {
    "status": "error",
    "error_type": "NOT_FOUND",
    "message": "Resource note_099 does not exist",
    "retryable": false,
    "suggested_action": "Check existing note IDs with notes.list"
  }
  ```

---

### Issue 18: Configuration, Secret, and Token File Fragmentation
- **Location:** `.env`, `.google_token.json`, `.gmail_token.json`, `client_secret.json`, `config.py`.
- **Observed Behavior:** Credentials are saved in scattered flat files across the root repository directory.
- **Root Cause Analysis:**
  Multiple services read tokens from different paths without unified secret loading or permissions checks. Storing tokens directly in the workspace root creates an accidental commit risk.
- **Architectural Remedy:**
  Centralize all configuration and tokens in a dedicated, Git-ignored `storage/secrets/` directory or platform keyring, managed by a unified `Settings` service.

---

### Issue 19: Complete Absence of Execution Identity
- **Location:** `state.py`, `graph.py`, `main.py`.
- **Observed Behavior:** No tracking of user, conversation, or step identity across graph cycles.
- **Root Cause Analysis:**
  The system has `request_id` and `trace_id`, but completely lacks:
  - `user_id` (assumes single local user everywhere)
  - `conversation_id` / `session_id` (all chats overwrite one file)
  - `execution_id` (no run isolation)
  - `plan_id` & `step_id` (no idempotency keys for tool side-effects)
- **Architectural Remedy:**
  Thread a mandatory execution context object through every layer:
  `ExecutionContext(user_id, session_id, execution_id, step_id)`.

---

## 4. Architectural Debt Matrix & Transition Strategy

| Component | Architecture Role in V1 | Problem in V1 | Target Action in V2 | Target Module |
|---|---|---|---|---|
| **Graph State** | Monolithic `AgentState` with 38 fields | Clashing reducers, in-place list mutation, missing identities | **Replace** with clean typed state | `app/state/` |
| **Planner Node** | 1,050-line ReAct + DAG + heuristics monolith | Bloat, argument guessing, hardcoded bypasses | **Replace** with modular planner | `app/planning/` |
| **Tool Registry** | Substring keyword matching | Insecure authorization bypass | **Replace** with typed Tool Gateway | `app/gateway/` |
| **Approval Flow** | Reruns graph with blanket flag | TOCTOU vulnerability, lost context | **Replace** with checkpoint approval | `app/execution/` |
| **Memory System** | Flat JSON + standalone FAISS | Single-tenant, race conditions, file clobbering | **Replace** with relational/vector store | `app/knowledge/` |
| **RAG Pipeline** | Pickle BM25 + unanchored FAISS | Insecure deserialization, no citation verification | **Refactor** with verified citation pipeline | `app/retrieval/` |
| **Observability** | In-place mutated trace list in state | Quadratic duplication, corrupted traces | **Decouple** from graph state | `app/observability/` |
| **Calendar MCP** | Divergent mock and real servers | Schema mismatch, duplicate tools | **Unify** behind single Calendar Gateway | `app/integrations/calendar/` |
| **Gmail MCP** | Unconfirmed live email operations | High risk, out of initial scope | **Deactivate** from initial V2 surface | N/A (Deferred) |
| **Web Fetch MCP**| Insecure `urllib` fetcher | SSRF, cloud metadata access | **Harden** with IP-level filtering | `app/tools/fetch.py` |
| **SQLite MCP** | F-string SQL interpolation | SQL injection risk | **Harden** with parameterized statements | `app/tools/sqlite.py` |

---

## 5. Conclusion & Transition Authorization
The Phase 0 audit confirms that the existing implementation cannot be stabilized with minor surface bugfixes. The core architectural contradictions (state reducer clashing, insecure approval rerun, heuristic argument guessing, substring security policies, and unpartitioned storage) require a controlled, principled migration to a clean V2 architecture.

The next immediate priority is the establishment of the **Evaluation Baseline (`benchmarks/v2/`)** to empirically record the performance and failure rates of the existing system prior to executing code changes.
