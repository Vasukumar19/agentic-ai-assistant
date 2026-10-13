# V2 Architecture & Security Remediation Defect Log

## Baseline Commit
`6db89eb28f4917d92f1d34b61aa53f1b0b1f2ea6` (Branch: `remediation/v2-hardening`)

---

## Status Definitions
- `FIXED_AND_TESTED`: The defect has been corrected at the architectural root cause and verified with passing unit/integration regression tests and benchmark tasks.

---

## Remediated Defect Matrix

### Priority 0: Authentication and Identity Security

- **DEF-01: Caller-Controlled User Identity & Missing Authentication Boundary**
  - *Location*: `app/api/server.py`, `app/core/auth.py`, `app/core/context.py`, `app/assistant.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Implemented `UserPrincipal` and FastAPI dependency `get_current_principal`. Header-derived identity (`Authorization: Bearer <key>` or `X-User-Id` / `X-Dev-User`) with administrative impersonation controls (`impersonate_user()`). In production mode, unauthenticated or unauthorized requests fail closed with HTTP 401/403. Removed unauthenticated caller-controlled identity injection from all endpoints.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_production_mode_unauthenticated_fails_closed`, `test_cross_tenant_note_isolation`, `test_cross_tenant_reminder_isolation`, `test_cross_tenant_approval_denied`.

---

### Priority 1: CORS, API Validation, and Error Handling

- **DEF-02: Insecure Wildcard CORS with Credentials**
  - *Location*: `app/api/server.py`, `app/core/config.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Hardened `CORS_ORIGINS` to require explicit origins in production. Lifespan validator strictly prohibits wildcard `*` when `allow_credentials=True` or `ENVIRONMENT="production"`.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_production_startup_rejects_wildcard_cors`.

- **DEF-03: Raw Exception Leaking in API Responses**
  - *Location*: `app/api/server.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Replaced raw `str(exc)` exposure with standard sanitized `ErrorResponseEnvelope` containing typed error codes and correlation IDs, logging full traces securely server-side.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_safe_error_handling_hides_raw_exception`.

- **DEF-04: Weak / Missing Request Validation**
  - *Location*: `app/api/server.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Added Pydantic field bounds (`min_length=1`, `max_length=4000`), ISO-8601 UTC timezone parsing on reminder `due_date`, and strict input model validation across all endpoints.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_validation_rejects_empty_query`, `test_validation_rejects_malformed_due_date`.

---

### Priority 2: Cryptographic Approval Correctness

- **DEF-05: Hardcoded HMAC Secret Default**
  - *Location*: `app/core/config.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Lifespan startup check validates `APPROVAL_HMAC_SECRET` length (>= 32 characters) and rejects hardcoded default secrets in production mode, failing closed immediately.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_production_startup_rejects_weak_hmac_secret`.

- **DEF-06: Approval Token Binding & Canonical Integrity Flaw**
  - *Location*: `app/gateway/approval.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Expanded token format to full 256-bit digest (`tok_{action_id}_{sig64}`). Added canonical payload serialization rehashing in `validate_and_consume` to detect database payload tampering before execution.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_tampered_argument_payload_rejected`.

- **DEF-07: Non-Atomic Approval State Transition (Race Condition & Replay Risk)**
  - *Location*: `app/gateway/approval.py`, `app/storage/database.py`, `app/storage/models.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Database migration added `risk_level`, `executed_at`, and `execution_outcome` columns. `validate_and_consume` performs single-turn atomic state transition (`consumed=True`, `status="APPROVED"`) with rollback on failure, eliminating replay attacks.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_approval_atomic_single_consumption`.

- **DEF-08: Approval Execution Resumes Generic Prompt Rather Than Exact Persisted Action**
  - *Location*: `app/api/server.py`, `app/gateway/approval.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: `/api/approvals/approve` validates user ownership of the pending action and dispatches the exact persisted tool name and arguments through `gateway.dispatch(..., approval_token=req.token)`, recording execution outcomes.
  - *Regression Test*: `tests/v2/test_stage5_presentation.py::test_api_chat_approval_gating`, `benchmarks/v2/tasks.py::TASK_ACT_04`.

---

### Priority 3: Execution and Verification

- **DEF-09: Unsafe Query-Pattern Regex & Fabricated Resource IDs**
  - *Location*: `app/orchestration/deliberate_path.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Removed hardcoded fallback IDs (`note_101`, `rec_id=2`, `due_date="2026-10-20 18:00"`). Missing IDs trigger explicit user clarification prompts rather than fabricated execution.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_deliberate_path_rejects_missing_note_id`, `test_deliberate_path_rejects_missing_sqlite_id`.

- **DEF-10: Weak Outcome Verification**
  - *Location*: `app/orchestration/verifier.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Upgraded `OutcomeVerifier` to postcondition-based verification returning typed `VerificationResult` with statuses: `COMPLETE`, `INCOMPLETE`, `BLOCKED`, `FAILED`, and `UNKNOWN`.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_outcome_verifier_states`.

- **DEF-11: Tool Result Masking (Error Strings Wrapped as Success)**
  - *Location*: `app/gateway/dispatcher.py`, `app/gateway/manifest.py`, `app/tools/fetch.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Structured `ToolResultEnvelope.error` correctly with typed `ToolErrorCode` enum and side-effect tracking (`side_effect_occurred`).
  - *Regression Test*: `tests/v2/test_stage2_gateway.py::test_tool_dispatcher_schema_validation`.

- **DEF-12: Incomplete Tool Manifest Input Schema Validation**
  - *Location*: `app/gateway/manifest.py`, `app/gateway/dispatcher.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Implemented JSON Schema argument validation (`jsonschema.validate` with standard fallback) asserting types, string length, and format before dispatch.
  - *Regression Test*: `tests/v2/test_stage2_gateway.py::test_tool_dispatcher_schema_validation`.

---

### Priority 4: Reminder Implementation

- **DEF-13: Silent Reminder Due Date Corruption**
  - *Location*: `app/gateway/bootstrap.py`, `app/api/server.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Normalized date parsing preserving requested timestamps, converting local offsets to UTC, and raising validation errors on invalid inputs rather than defaulting to `now()`.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_reminder_due_date_preserved_accurately`.

- **DEF-14: Missing Persistent Reminder Scheduler**
  - *Location*: `app/services/reminder_scheduler.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Implemented `PersistentReminderScheduler` background daemon with atomic row claiming (`status = 'DELIVERING' -> 'DELIVERED'`), retry tracking, and restart recovery.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_persistent_reminder_scheduler_delivers_due_jobs`.

---

### Priority 5: SSRF and Filesystem Isolation

- **DEF-15: SSRF DNS Rebinding & Unsafe Redirects in HTTP Fetcher**
  - *Location*: `app/tools/fetch.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Implemented socket IP pinning directly preventing TOCTOU DNS rebinding. Expanded blocked ranges (IPv4 loopback, RFC1918, link-local, cloud metadata 169.254.169.254, multicast, broadcast, and IPv4-mapped IPv6 `::ffff:0:0/96`). Disabled automatic redirects.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_ssrf_detects_all_blocked_network_ranges`, `test_ssrf_blocks_private_destinations`.

- **DEF-16: Filesystem Sandbox User Directory Collision & Path Security**
  - *Location*: `app/tools/filesystem.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Replaced character-replacement regex with SHA256 tenant jail mapping (`u_{sha256(user_id)[:16]}`). Validated symlink targets against canonical jail root and enforced write quotas.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_filesystem_collision_resistant_mapping`, `test_filesystem_sandbox_traversal_blocked`.

---

### Priority 6: Storage and Integrations

- **DEF-17: Production Code Imports Benchmark Fixtures**
  - *Location*: `app/services/calendar.py`, `app/gateway/bootstrap.py`, `app/orchestration/deliberate_path.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Created isolated `LocalCalendarService` and eliminated all imports of `DETERMINISTIC_CALENDAR`, `DETERMINISTIC_NOTES`, and `DETERMINISTIC_REMINDERS` from production runtime code.
  - *Regression Test*: Clean production imports verified across `app/`.

- **DEF-18: Inaccurate Storage Claims**
  - *Location*: `app/core/config.py`, documentation, `README.md`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Updated docstrings, settings, and documentation to accurately describe the local-first SQLite WAL architecture (`assistant_v2.db`) rather than unconfigured pgvector.

---

### Priority 7: Telemetry, RAG & Citations

- **DEF-19: Fabricated LLM Telemetry**
  - *Location*: `app/assistant.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Eliminated `[{"total_tokens": 150}]` hardcoded placeholder. Latencies measured monotonically via `time.perf_counter()`. Trace events extracted genuinely from observability sink.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_assistant_invoke_monotonically_timed_and_not_fabricated`.

- **DEF-20: Missing Real Provenance Citation Validation**
  - *Location*: `app/knowledge/retriever.py`, `benchmarks/v2/tasks.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Implemented `validate_citation_provenance()` asserting tenant document ownership, chunk existence, and excerpt content match. Integrated into evaluation oracles.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_provenance_citation_validation`.

---

### Priority 8 & 9: Benchmark Isolation & Oracles

- **DEF-21: Benchmark Fixtures Mutate Real & Legacy Storage**
  - *Location*: `benchmarks/v2/fixtures.py`, `benchmarks/v2/runner.py`, `benchmarks/v2/tasks.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Stopped mutating legacy files. Benchmarks now seed and tear down isolated relational tenants (`usr_bench_{task_id}`) per task. Invokes assistant through official `app.invoke()` contract. Oracles assert database state changes and provenance.
  - *Verification*: Full 50-task evaluation benchmark (`benchmarks/v2/runner.py`) passed 50/50 with zero state corruptions, zero bypasses, and authentic metrics.

---

### Priority 10: Deep Hardening & Staff-Level Remediation (Stage 3)

- **DEF-22: Synthetic Test Token Backdoor in Production**
  - *Location*: `app/core/auth.py`, `app/core/config.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Evaluated `settings.AUTH_MODE` and `settings.ENVIRONMENT` strictly. In production mode, test tokens (`tok_test_admin_*`, `tok_test_user_*`) and developer headers are strictly rejected with 401 Unauthorized. Lifespan validator enforces `AUTH_MODE == "production"` whenever `ENVIRONMENT == "production"`.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_production_rejects_synthetic_admin_tokens`, `test_production_rejects_synthetic_user_tokens`, `test_production_rejects_inconsistent_auth_mode`.

- **DEF-23: Short API Key Prefix Collision in Identity Derivation**
  - *Location*: `app/core/auth.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Replaced `x_api_key[:6]` prefix slicing with full SHA-256 digest (`usr_apikey_{sha256(key)[:16]}`), guaranteeing collision-resistant principal identity.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_api_key_sha256_identity_collision_prevention`.

- **DEF-24: Staged Approval Execution States, Concurrency & Crash Recovery**
  - *Location*: `app/gateway/approval.py`, `app/gateway/dispatcher.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Expanded lifecycle states to `PENDING` -> `EXECUTING` -> `COMPLETED` / `FAILED` / `UNCERTAIN`. Atomic conditional update (`WHERE status = 'PENDING'`) prevents race conditions between simultaneous threads. Added `recover_stale_executing_approvals()` to safely transition interrupted executions to `UNCERTAIN` after system crashes.
  - *Regression Test*: `tests/remediation/test_p0_p1_p2_security.py::test_approval_multithreaded_concurrent_consumption`, `test_approval_lifecycle_states_and_crash_recovery`.

- **DEF-25: Incomplete Lifespan Lifecycle for ReminderScheduler**
  - *Location*: `app/api/server.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Wired `ReminderScheduler` into FastAPI `lifespan` handler. On application startup, recovers stale jobs stuck in `DELIVERING` from prior crashes and launches background polling worker; gracefully terminates thread on shutdown.
  - *Regression Test*: Validated FastAPI lifespan integration and clean start/stop lifecycle.

- **DEF-26: Dishonest Delivery Status for Unsupported Notification Channels & Stale Recovery**
  - *Location*: `app/services/reminder_scheduler.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Supported channels restricted to `CLI`, `LOCAL`, and registered adapters. Unconfigured external channels (e.g. `SLACK`, `EMAIL`) raise `NotImplementedError`, transitioning reminder to `FAILED` with explicit error details rather than falsely logging success. Implemented `recover_stale_delivering_reminders()` with bounded retries.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_reminder_scheduler_unsupported_channel_fails_truthfully`, `test_reminder_scheduler_stale_recovery`.

- **DEF-27: Broken Direct HTTPS Socket IP Pinning (`set_tunnel` on Direct HTTPS)**
  - *Location*: `app/tools/fetch.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Replaced incorrect proxy tunneling (`set_tunnel(hostname)`) on `HTTPSConnection` with `PinnedHTTPSConnection`, creating a raw TCP socket to pinned destination IP and wrapping it via `ssl_ctx.wrap_socket(sock, server_hostname=hostname)`. Direct TLS connection preserves SNI and verifies certificates without proxy overhead or socket errors.
  - *Regression Test*: Tested direct pinned TLS handshake against public HTTPS endpoints and local SSRF blocked ranges.

- **DEF-28: Cross-Document Citation Provenance Mismatch Hole**
  - *Location*: `app/knowledge/retriever.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Enforced `chunk.document_id == citation.document_id` and `chunk.document_id == doc.document_id` in `validate_citation_provenance()`. Required non-empty `exact_quote` and normalized whitespace substring matching.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_citation_mismatched_document_id_rejected`, `test_citation_empty_quote_rejected`.

- **DEF-29: Loose / Weak Benchmark Evaluation Oracles**
  - *Location*: `benchmarks/v2/tasks.py`, `benchmarks/v2/runner.py`, `benchmarks/v2/schema.py`
  - *Status*: `FIXED_AND_TESTED`
  - *Remediation*: Repaired doc QA oracles to enforce database citation provenance verification (`prov_valid is True`). Replaced single-keyword calendar assertions with multi-event matching. Enforced bounded execution with valid termination in budget test. Distinguish unavailable token telemetry from fabricated zero tokens. Added negative controls.
  - *Regression Test*: `tests/remediation/test_p3_p4_p5_execution.py::test_oracle_negative_controls`.
