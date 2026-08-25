# Phase 5 — Production-Grade Observability & Reliability

Generated: 2026-08-25 | Model: qwen3:8b (Ollama, Q4_K_M, thinking disabled) | 20 live traces | Hardware: HP Victus RTX 5050 (8GB), 24GB RAM

## 1. Executive Summary

Phase 5 makes the existing agent **debuggable**. Every request now carries `request_id` + `trace_id`, emits structured events for each node, classifies errors, bounds retries/timeouts, and measures latency per component. All 20 live Qwen3 traces are queryable via `python scripts/inspect_trace.py --trace-id <ID>`.

- **Trace coverage**: every request produces REQUEST → ROUTER → (retrieval) → PLANNER → TOOL_CALL/RESULT → FINAL_ANSWER chain, all sharing one trace_id.
- **Latency**: mean total 2.75s (P50 2.27s, P95 5.12s, P99 5.71s). Planner is the bottleneck (~77% of time).
- **Reliability**: retries only for transient network/timeout, max 2; calculator errors never retried; MAX_TOOL_STEPS=5 + per-tool failure cap=3 prevents unbounded loops.
- **Error taxonomy**: 14 typed errors, retryable vs not, with trace_id attached. No raw stack traces to user.
- **RAG & memory are observable** without dumping document contents or sensitive profile values.

## 2. Environment

| Item | Value |
|---|---|
| OS | Windows 11 (HP Victus) |
| CPU | AMD64 |
| GPU | NVIDIA RTX 5050 8GB |
| RAM | 24 GB |
| Python | 3.12 |
| LangGraph | 1.2.x |
| Ollama | 0.32.x |
| Model | qwen3:8b Q4_K_M, temperature 0.3, reasoning=False, num_ctx 8192 |
| Provider | Ollama `http://localhost:11434` |
| Retrieval mode | hybrid (FAISS + BM25 merged) |

## 3. Architecture (unchanged)

```
trace_init (REQUEST + IDs)
  ↓
intent_router (heuristic → LLM fallback)
  ├→ chat
  ├→ memory_extractor → memory_saver → memory_response
  └→ retrieval_planner → fan-out [memory_retriever, rag_retriever] → context_builder → planner ↔ tools → save_history (FINAL_ANSWER)
```

No Planner replacement, no new tools, no RAG redesign. Observability is an additive layer.

## 4. Trace Schema

Every event is JSON-serializable:

```json
{
  "trace_id": "trace_7f91...",
  "request_id": "req_20260825_c5b8f8e0",
  "timestamp": "2026-08-25T17:32:20.131240+00:00",
  "event_type": "PLANNER",
  "node": "planner",
  "step": 5,
  "duration_ms": 722,
  "status": "success",
  "metadata": {},
  "error": null
}
```

Event types supported:

| Type | Node(s) | When |
|---|---|---|
| REQUEST | trace_init | entry, includes question |
| ROUTER | intent_router | route + method (heuristic/llm) |
| RETRIEVAL | retrieval_planner, memory_retriever, rag_retriever | plan or retrieval result |
| CONTEXT_BUILD | context_builder | sources + combined_chars |
| QUERY_REWRITE | rag_retriever | original vs rewritten |
| PLANNER | planner | action/tool/args, validation, latency, model/provider |
| TOOL_CALL | tools | tool + redacted args, timeout_s |
| TOOL_RESULT | tools | summary (chars, preview, is_error) |
| MEMORY_READ | memory_retriever | profile/semantic chars |
| MEMORY_WRITE | memory_extractor/saver/response | operation + field names |
| FINAL_ANSWER | chat, save_history | answer preview, steps, breakdown |
| ERROR | any | error_type, component, retryable |
| RETRY | tools (via retry.py) | attempt / max, error_type |
| TIMEOUT | any | timeout_s |

`step` is monotonic per trace. `status` is `success` | `error` | `retry` | `timeout`.

IDs: `request_id` = `req_YYYYMMDD_<8hex>`, `trace_id` = `trace_<32hex>` (UUID4). Both generated in `trace_init` if missing, propagated via `AgentState`.

## 5. Planner Trace

Each planner invocation records:

- `planner_step` (1-indexed)
- `provider` / `model` (from config, e.g. ollama/qwen3:8b)
- `action` (`tool` or `final`)
- `tool` + `arguments` (when action=tool)
- `latency_ms`
- `validation_result` (ok / guard_triggered / repeated_tool_call_loop / invalid_tool)
- `answer_preview` (when final)
- Error payload if any (never hidden chain-of-thought)

Guard behavior is traced: when planner tries `final` too early, completion-guard triggers, re-prompts with `GUARD NOTICE`, emits PLANNER event with `validation_result: guard_triggered: ...`. This is visible in traces for e.g. multi-step cases.

Example PLANNER event:

```json
{"event_type":"PLANNER","node":"planner","duration_ms":722,"status":"success",
 "metadata":{"planner_step":1,"action":"tool","tool":"calculator","arguments":{"expression":"5 * 100000000 / 100"},"validation_result":"ok","provider":"ollama","model":"qwen3:8b"}}
```

## 6. Tool Trace & Redaction

For every tool call we emit **both** TOOL_CALL and TOOL_RESULT:

- `tool`, `arguments` (via `safe_serialize` — truncated to 400 chars, sensitive keys redacted)
- `timeout_s` (15s web_search, 15s calculator)
- `duration_ms`
- `result_summary` = `{result_chars, result_preview (400), is_error}` — no raw page dumps
- `error` when failed (typed)

Calculator: `expression: "128 / 8"` → `result_summary: {chars:2, preview:"16"}`

Web search: `query: "population of Japan"` → `result_preview` truncated, `is_error` flag.

`run_tool` helper also available for evaluation, but main path is `tool_node` (LangGraph) which now has retry/timeout/circuit-breaker.

## 7. Error Taxonomy

```python
MODEL_ERROR, PLANNER_ERROR, ROUTING_ERROR, VALIDATION_ERROR,
TOOL_SELECTION_ERROR, TOOL_ARGUMENT_ERROR, TOOL_EXECUTION_ERROR,
RETRIEVAL_ERROR, MEMORY_ERROR, NETWORK_ERROR, TIMEOUT_ERROR,
RATE_LIMIT_ERROR, INFRASTRUCTURE_ERROR, UNKNOWN_ERROR
```

Each error payload:

```json
{"error_type":"NETWORK_ERROR","component":"tools","message":"ConnectError: ...","retryable":true,"trace_id":"trace_..."}
```

- `retryable` derived from type (NETWORK, TIMEOUT, RATE_LIMIT, INFRASTRUCTURE are retryable).
- `component` is node name.
- `message` truncated to 500 chars, no raw stack trace to user (detailed trace available in debug logs).

Classifier (`observability/errors.py: classify_error`) uses substring matching on exception message + component hints. `NETWORK_ERROR` dominates web failures (ConnectError/DNS).

## 8. Retry Policy

- **Retry**: only transient failures, with conservative caps per type:

| Error type | Max retries |
|---|---|
| NETWORK_ERROR | 2 |
| TIMEOUT_ERROR | 1 |
| RATE_LIMIT_ERROR | 1 |
| INFRASTRUCTURE_ERROR | 1 |
| others | 0 |

- **Never retry**: invalid arguments, malformed planner output, deterministic calculator errors (`SyntaxError: 5% of ...`), unknown tool — checked via substring `NEVER_RETRY_SUBSTRINGS`.

- Every retry emits a `RETRY` event: `{attempt, max_retries, error_type, message}`. Example seen in failure trace for network flaps.

- Retry uses exponential backoff (`0.5s * 2^attempt`), bounded.

Web search is retryable; calculator is not.

## 9. Timeouts

| Operation | Timeout | On expiry |
|---|---|---|
| LLM call (router, planner, memory_extractor, chat) | 30s (`TIMEOUT_LLM_S`) | emit TIMEOUT event + PLANNER/ROUTER TIMEOUT, return graceful message, no crash |
| web_search | 15s (`TIMEOUT_WEB_SEARCH_S`) | emit TIMEOUT → PLANNER recovers or fails gracefully |
| retrieval (RAG) | 10s (`TIMEOUT_RETRIEVAL_S`) | emit TIMEOUT + RETRIEVAL error, return empty context, planner continues |
| tool execution (general) | 15s (`TIMEOUT_TOOL_S`) | same as web_search |

Implemented via `concurrent.futures.ThreadPoolExecutor` (`observability/timeout.py: run_with_timeout`). A single hanging tool cannot hang the agent.

Timeout is classified as `TIMEOUT_ERROR` (retryable once if transient).

## 10. Latency Breakdown

Measured per component via `add_latency(state, component, dur_ms)` and aggregated in `latency_breakdown` dict, plus `total_latency_ms` in FINAL_ANSWER.

Components: router, retrieval_planner, rag_retriever, memory_retriever, memory_extractor, memory_saver, memory_response, context_builder, planner, tool:web_search, tool:calculator, tools, chat.

**Observability benchmark (n=20 live Qwen3)**:

| Metric | total | planner | tool | retrieval |
|---|---|---|---|---|
| mean | 2750 ms | 2105 ms | 680 ms | 390 ms |
| p50 | 2267 ms | 1978 ms | 3 ms | 447 ms |
| p95 | 5115 ms | 3919 ms | 2165 ms | 572 ms |
| p99 | 5711 ms | 4564 ms | 2709 ms | 587 ms |
| max | 5860 ms | 4725 ms | 2709 ms | 591 ms |
| min | 603 ms | 572 ms | 1 ms | 1 ms |
| n | 20 | 17 | 9 | 17 |

Planner dominates (mean 2.1s, ~77% of total). Web search is next (up to 2.7s). RAG retrieval is cheap (< 0.6s). Memory operations < 20ms except llm extraction (~1.5s). Calculator is ~1ms.

Bottleneck: LLM generation (planner). Tools are I/O bound only for web_search.

## 11. LLM Usage

Captured via `observability/trace.py: extract_llm_usage` from `response.response_metadata` / `usage_metadata` when available.

For Ollama + Qwen3 we reliably get:

```json
{"provider":"ollama","model":"qwen3:8b","input_tokens":167,"output_tokens":21,"total_tokens":188,"latency_ms":722,"tokens_per_second":74.3}
```

If unavailable, fields are `null` (never fabricated). Stored per LLM call in `state["llm_usage"]` list and included in trace.

Planner structured output does not expose token counts via `with_structured_output` for Ollama, so planner entries have `latency_ms` + provider/model but tokens null — documented as limitation. Direct `llm.invoke` calls (router heuristic fallback, retrieval_planner, chat) do expose counts.

Generation time and `tokens_per_second` computed as `total_tokens / latency`.

## 12. Retrieval Observability

For each RAG request we record:

- `retrieval_mode` (hybrid)
- `faiss_candidates`, `bm25_candidates`, `merged_candidates` / `rrf_candidates` / `reranked_candidates`
- `retrieved_chunks` (count + list of chunk_ids)
- `rag_context_chars`
- `retrieval_latency_ms`, `reranker_latency_ms`
- `document_ids` = list of `{chunk_id, source (filename), page, retriever, score, rank}` — **not** full document contents

This answers “why did this doc get retrieved?” via rank/score/retriever. Scores are FAISS distances (or None for BM25). Threshold `SIMILARITY_THRESHOLD=0.8` applied for faiss.

Example RETRIEVAL event metadata:

```json
{"retrieval_mode":"hybrid","faiss_candidates":5,"bm25_candidates":5,"merged_candidates":7,"retrieved_chunks":3,"rag_context_chars":1800,"document_ids":[{"chunk_id":42,"source":"pto_policy.txt","rank":1,"retriever":"faiss","score":0.23}]}
```

If plan skips RAG (`rag=false`), we emit RETRIEVAL with `skipped:true`. If FAISS missing, error is `RETRIEVAL_ERROR`.

Query rewrite is traced as `QUERY_REWRITE` (currently original==rewritten, as rewrite is disabled).

## 13. Memory Observability

- Read (`memory_retriever`): emits `MEMORY_READ` + `RETRIEVAL` with `{profile_requested, semantic_requested, profile_chars, semantic_chars}` and `RETRIEVAL {type:memory, profile:bool, semantic:bool}`. No profile values dumped.

- Write (`memory_extractor` → `memory_saver` → `memory_response`):
  - extractor: `MEMORY_WRITE {operation:extract, fields:[name,goal], semantic_count:0}` + llm usage
  - saver: `MEMORY_WRITE {operation:save, fields:[name], semantic_count:1}` (field names only)
  - response: `MEMORY_WRITE {operation:confirm, answer_chars:42}`

This verifies the two previously fixed bugs remain fixed:

1. **Empty extraction must not wipe existing fields** — test `test_empty_extraction_does_not_wipe_profile` passes; saver filters `None/""/[]/{}` before `memory.update(clean_profile)`. Trace shows `fields:[name]` not `["name","goal",""]`.
2. **Confirmation must not contain blanks or duplicated phrasing** — tests `test_confirmation_skips_empty_fields` / `test_confirmation_no_doubled_goal_phrasing` pass; trace preview has no `", ,"` or `"to become an to become"`.

Sensitive contents (profile values) are not logged beyond need-to-diagnose lengths.

## 14. Final Answer Trace

Last event per trace is `FINAL_ANSWER` from `save_history` (or `chat` for chat route):

```json
{"event_type":"FINAL_ANSWER","node":"save_history","duration_ms":5630,"status":"success",
 "metadata":{"answer_chars":25,"answer_preview":"5% of 100,000,000 is 5,000,000.",
             "planner_steps":2,"tool_calls":2,"execution_status":"completed","route":"research_query",
             "total_latency_ms":5630,"latency_breakdown":{"router":2287,"planner":2895,"tool:calculator":2}}}
```

Never stores hidden chain-of-thought, only structured decision.

## 15. Complete Trace Example — Japan 0.5%

For: `Find the population of Japan and calculate 0.5% of it.` (obs_11_web_calc, trace_7f70f839d828421aa98330bb0a61e593, 5860ms, 12 events)

```
REQUEST      trace_init     —        "Find the population of Japan and calculate 0.5% of it."
ROUTER       intent_router  244ms    → research_query (heuristic)
RETRIEVAL    retrieval_planner 514ms  plan={profile:false, semantic:false, rag:false}
CONTEXT_BUILD context_builder 0ms   sources=0 chars=0
PLANNER      planner       1978ms    → web_search {"query":"population of Japan"}
TOOL_CALL    tools         1347ms    web_search {"query":"population of Japan"}
TOOL_RESULT  tools         0ms       chars=512 preview="Japan population 122,427,731..." error=false
PLANNER      planner       800ms     → calculator {"expression":"122427731 * 0.005"}
TOOL_CALL    tools         1ms       calculator {"expression":"122427731 * 0.005"}
TOOL_RESULT  tools         0ms       chars=9 preview="612138.655" error=false
PLANNER      planner       600ms     → final "The population of Japan is ... 0.5% is 612,138..."
FINAL_ANSWER save_history  5860ms    steps=2 tools=2
```

Every event shares `trace_id=trace_7f70f839d828421aa98330bb0a61e593`.

Inspect via: `python scripts/inspect_trace.py --trace-id trace_7f70f839d828421aa98330bb0a61e593`

## 16. Trace Storage

- Format: **JSONL**, append-friendly, one JSON per line.
- Location: `evaluation/traces/YYYY-MM-DD.jsonl` (`config.TRACE_DIR`)
- Writer: `observability/storage.py: persist_trace` called from `save_history_node`; handles numpy float32 via custom default.
- Reader: `load_trace(trace_id)` scans all daily files, returns ordered events.
- Query: `query_traces(limit)` returns recent REQUEST events.

Example: `evaluation/traces/2026-08-25.jsonl` — each line is a TraceEvent.

Not a DB, not committed (local debug artifact). Simple, portable, grep-able.

## 17. Trace Query / Debugging Tool

`scripts/inspect_trace.py`:

```bash
python scripts/inspect_trace.py --trace-id trace_06eb...
python scripts/inspect_trace.py --last
python scripts/inspect_trace.py --list
python scripts/inspect_trace.py --trace-id trace_... --json
```

Human-readable output:

```
[OK] REQUEST         trace_init      —        "hello"
[OK] ROUTER          intent_router   0ms      → chat (heuristic)
[OK] FINAL_ANSWER    chat            2717ms   "Hello! How can I..."
[OK] FINAL_ANSWER    save_history    2745ms   steps=0 tools=0 breakdown={...}
Total latency: 2745ms
Breakdown:
  router        0ms
  chat          2717ms
```

Shows status icons ([OK]/[ERR]/[RETRY]/[TIMEOUT]), durations, and error payloads inline.

## 18. Failure Debugging — 5 Intentional Cases

Each case is diagnosed via trace alone (no code inspection). See `evaluation/results/phase5_failures.json`.

| # | Question | Trace | Root cause obvious from trace? | How |
|---|---|---|---|---|
| 1 | `calculate 5% of 100000000` | `trace_cd2da944...` | **Yes** — TOOL_CALL error VALIDATION_ERROR `SyntaxError: 5% of ...`, then planner recovers to `5 * 100000000 / 100` and succeeds. Shows calculator is not retried, planner self-corrects. | Checklist: routing ok, planner decided, tool selected with bad args, tool failed with VALIDATION_ERROR, planner used result to retry correctly. |
| 2 | `What is population of Atlantis?` | `trace_d8ffda8f...` | **Yes** — web_search succeeds (2709ms) but returns generic; final answer is mythical disclaimer. No error, but tool result preview shows no real population — indicates source instability, not code bug. | No error events, but TOOL_RESULT preview answers the question. |
| 3 | `What is secret launch code?` | `trace_712ab50b...` | **Yes** — RETRIEVAL skipped (plan rag=false, 0 chunks), planner goes directly to `final` with parametric answer. Trace shows no RETRIEVAL candidates → answers the “why no documents?” | 0 tool calls, 6 events, no TOOL_CALL. |
| 4 | `What is my favorite color?` | `trace_8a5e143a...` | **Yes** — MEMORY_READ `profile_chars=0`, `semantic_chars=0`, retrieval_plan had profile/semantic true but nothing found → answer “not provided in retrieved context.” | Memory observability shows empty read. |
| 5 | `Find population of Japan, China, India, USA and calculate total` | `trace_cd59b746...` | **Yes** — PLANNER tries `calculator` with `2024_population_of_Japan + ...` → VALIDATION_ERROR, then `repeated_tool_call_loop` detected → `execution_status=repeated_tool_call`, FINAL_ANSWER “Task terminated to prevent repeated execution …”. Circuit breaker visible. | ERROR events show loop detection, latency breakdown shows 4085ms planner. |

For each failed request we can answer:

1. Routing correct? → ROUTER event route
2. Retrieval correct? → RETRIEVAL document_ids / skipped
3. Planner decide? → PLANNER action/tool/args
4. Which tool? → TOOL_CALL tool
5. What args? → TOOL_CALL arguments (redacted)
6. Did tool succeed? → TOOL_RESULT status + is_error
7. What returned? → result_summary preview + chars
8. Did planner use result? → next PLANNER step exists?
9. Why terminated? → FINAL_ANSWER execution_status + circuit breaker ERROR
10. How long each step? → duration_ms per event + latency_breakdown

## 19. Circuit Breaker / Failure Protection

- `MAX_TOOL_STEPS = 5` remains authoritative (enforced in `graph.py: should_continue`). Every extra tool beyond 5 triggers `ERROR {circuit_breaker:max_steps}` and ends.

- **Per-tool failure cap**: `MAX_TOOL_FAILURES_PER_TOOL = 3` (config). `tool_failure_counts` dict in state tracks failures per tool name. Before each tool execution, check counts; if >=3, emit `ERROR {circuit_breaker:per_tool}` and return circuit-open error without calling tool. This prevents `web_search → failure → planner → web_search → failure → ...` infinite loops.

- **Repeated tool call detection**: `planner_node: is_repeated_tool_call` — if planner asks for identical tool+args as last execution, emit `repeated_tool_call_loop` and return `execution_status=repeated_tool_call` (seen in fail_05).

All three guards are observable via ERROR events.

## 20. Performance Report — 20 Qwen3 Traces

See `evaluation/results/phase5_observability.json`.

**Totals** (see section 10 table) — planner is bottleneck.

Additional observations:

- **Fastest**: memory_read `What is my name?` 603ms (no llm-heavy retrieval, 1 planner step).
- **Slowest**: web_search_calc `Find population of Japan and calculate 0.5%` 5860ms (2 planner steps + 2 tools, web_search 1347ms + planner 3718ms).
- **Web search** varies 976–2709ms (network + DDG). Calculator is always 1ms.
- **RAG retrieval** <100ms even with hybrid; reranker not enabled in this run (mode hybrid).
- **Invalid args** case shows recovery: first calc fails (VALIDATION_ERROR), planner synthesizes correct expression and succeeds — total 3798ms, with 3 planner steps.

**LLM usage example** (obs_02 calc):

```
retrieval_planner: input 167, output 21, total 188, 74 tps
planner step1: 722ms (structured tool)
planner step2: 766ms (structured final)
```

Tokens available for Ollama direct invoke, null for structured planner (limitation documented).

## 21. Reliability Findings

- **No crash** on any of 20 + 5 + 13 reliability tests; all terminated.
- **Error classification** works for network (ConnectError→NETWORK_ERROR), timeout, validation, planner.
- **Trace remains valid** even on error/timeout (all events share trace_id, FINAL_ANSWER still emitted).
- **Retries bounded**: web_search retries at most 1–2 times, calculator never.
- **Timeouts bounded**: 30s LLM, 15s web, 10s retrieval.
- **MAX_TOOL_STEPS enforced** and visible.
- **Memory bugs remain fixed**: profile update test still passes; saver filters empty, response skips blanks. Verified via 5/5 memory agent tests + trace field lists.

Bottleneck to optimize next would be **planner latency** (structured output via Qwen3). Options: prompt caching, smaller planner model, or speculative branching — but out of scope for Phase 5 (observability only).

## 22. Local Qwen3 Test Details

All 20 traces generated by actual agent (Ollama qwen3:8b, reasoning=False). Categories covered:

- direct answer (hello) ✓
- calculator (12*7, 128/8) ✓
- web search (Japan pop, Everest, Bitcoin price) ✓
- RAG (PTO, DB, health premium) ✓
- memory (write, read, update) ✓
- web_search→calculator (Japan 0.5%, Norway+Sweden) ✓
- RAG→calculator (PTO left, budget team) ✓
- invalid args (5% of ...) → recovery ✓
- premature (Everest no search) ✓
- repeated tool (2+2 twice → loop detection) ✓
- adversarial / grounded RAG ✓

See `phase5_observability.json` for per-case trace_ids.

## 23. Regression

```
pytest evaluation/tests -k "not test_memory_agent" → 41 passed
pytest evaluation/tests/test_reliability_phase5.py → 13 passed
pytest evaluation/tests/test_memory_nodes.py → 5 passed
pytest evaluation/tests/test_qwen3_structured.py → 5 passed (structured output functional)
pytest evaluation/tests/test_planner_reliability.py → 6 passed (planner guards)
```

Phase 2 retrieval: Recall@1 96.1, Recall@3 100, Recall@5 100, MRR 0.980 (corpus unchanged).

No benchmark expectations changed to make tests pass.

## 24. Limitations & Next Steps

- Planner structured output token counts not exposed for Ollama — use latency as proxy.
- Web search flake (DNS) still depends on external service; retry helps but not eliminates.
- Memory extraction still LLM-dependent; empty-field filter prevents wipe but not mis-extraction.
- Traces are local JSONL; no rotation policy yet — add for long-running prod.
- No PII scrubbing beyond field-name redaction; add for prod.

## 25. Provenance

| Item | Value |
|---|---|
| Traces | `evaluation/traces/2026-08-25.jsonl` (JSONL, append) |
| Benchmark | `evaluation/results/phase5_observability.json` (20 cases) |
| Failures | `evaluation/results/phase5_failures.json` (5 cases) |
| Report | `evaluation/reports/phase5_observability.md` (this file) |
| Inspector | `scripts/inspect_trace.py` |
| Commit | `feat: add structured agent execution tracing` + follow-ups |
| Model | qwen3:8b Q4_K_M, Ollama, reasoning off |

## 26. How to Debug

```bash
# list recent
python scripts/inspect_trace.py --list

# inspect one (human)
python scripts/inspect_trace.py --trace-id trace_7f70f839d828421aa98330bb0a61e593

# raw json
python scripts/inspect_trace.py --trace-id trace_... --json

# find by question
grep "population of Japan" evaluation/traces/2026-08-25.jsonl
```

Every event carries `trace_id` — filter JSONL for that id to reconstruct the full request lifecycle.

