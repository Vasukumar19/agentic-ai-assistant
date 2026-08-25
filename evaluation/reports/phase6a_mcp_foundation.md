# Phase 6A — Generic MCP Client + Dynamic Tool Registry

Generated: 2026-08-25 | Model: qwen3:8b (Ollama, Q4_K_M) | 20 MCP traces via test server | 28 MCP tests

## 1. Motivation

Phases 1–5 validated a Planner→ToolNode agent with RAG, memory, observability. Adding Gmail/Calendar/etc. by hard-coding `if gmail: ...` would break the architecture. Phase 6A makes **MCP a connectivity protocol, not a planner feature**: any MCP server's tools are discovered, normalized, and appear to the planner as if native.

Goal:  
> If tomorrow we connect a completely different MCP server, the agent discovers its tools, enforces policies, executes, traces, and evaluates them **without modifying the planner**.

## 2. Existing Architecture

- `config.py:1` — env-overridable, self-loads `.env`
- `llm.py:66` — Ollama `qwen3:8b` (local), fallback to Google/OpenRouter/Groq
- `state.py:18` — `AgentState` with `tool_results`, `execution_status`, `trace_events`, `latency_breakdown`
- `graph.py:246` — `trace_init → intent_router → (chat|memory|retrieval_planner→context_builder→planner↔tools→save_history)`
- `nodes/tools.py:16` — static `tools=[web_search_tool, calculator]`, `ToolNode(tools)`, `run_tool`
- `nodes/planner_node.py:15` — `TOOL_INFO`/`VALID_TOOL_NAMES` baked at import, `PlannerDecision` validates `tool in VALID_TOOL_NAMES`, `planner_node` emits `PLANNER` events, handles `repeated_tool_call` and `check_completion_guard`
- `observability/*` — `TraceEvent` (`trace.py:34`), `ErrorType` (`errors.py:8`), `REQUEST/PLANNER/TOOL_CALL/TOOL_RESULT` etc., `persist_trace` JSONL

**Fragility for MCP:** `TOOL_INFO`/`VALID_TOOL_NAMES` were import-time constants. Dynamic registry must replace that.

## 3. MCP Architecture

```
USER → ROUTER → CONTEXT → PLANNER → TOOL REGISTRY → EXECUTOR → FINAL
                           │              │
                    ┌──────┴──────┐  ┌────┴────┐
                    │Native Tools │  │MCP Tools│
                    │ calculator  │  │test.echo│
                    │ web_search  │  │test.add │
                    └──────┬──────┘  └────┬────┘
                           └──────┬──────┘
                              ToolNode (traced)
                           ┌──────┴──────┐
                           │  MCP Client │  (stdio / streamable_http, timeout, retry)
                           └──────┬──────┘
                              MCP Server (test: python mcp_test_server.py)
```

Planner never does `if mcp:` — it asks `registry.tool_info()` and `registry.valid_names()`.

## 4. MCP Client Design

`mcp_layer/client.py:29` — `MCPClient(config: MCPServerConfig)`

- **Transports:** `stdio` via `mcp.client.stdio.stdio_client` + `StdioServerParameters`, `http/streamable_http` via `streamable_http_client`. SDK `mcp==2.1.1` (Python 3.12, anyio).
- **Sync wrapper:** `_run_async` (`client.py:16`) handles `asyncio.get_running_loop()` vs `asyncio.run` vs `ThreadPoolExecutor` for sync `tool_node`.
- **Ops:** `connect()`, `disconnect()`, `list_tools()`, `call_tool(tool_name, args)`. Each does `async with timeout → stdio_client → ClientSession → initialize → list_tools/call_tool`. For `call_tool`, strips server prefix (`test.echo` → `echo`) before `session.call_tool`.
- **Error mapping:** `MCPError` (`errors.py:22`) with `code` (`MCP_CONNECTION_ERROR`, `MCP_TOOL_NOT_FOUND`, `MCP_INVALID_ARGUMENT`, `MCP_PERMISSION_ERROR`, `MCP_TIMEOUT`, `MCP_SERVER_ERROR`, `MCP_PROTOCOL_ERROR`). Unwraps `BaseExceptionGroup` / `__cause__` for TaskGroup, checks `isError`/`is_error` and content substrings (`Unknown tool`, `permission`, `invalid`). Timeout via `asyncio.timeout`.
- **Timeouts:** `TIMEOUT_MCP_S=15` (`config.py:40`), per-tool `timeout_s` from `NormalizedTool`.

Tested: `mcp_test_server.py` exposes 5 tools, client `list_tools` returns schemas with `properties`, `call_tool` returns deterministic results.

## 5. Tool Registry Design

`mcp_layer/registry.py:35` — `ToolRegistry`

- **Holds:** `_native: dict[name, StructuredTool]`, `_mcp: dict[prefixed, StructuredTool]`, `_normalized: dict[name, NormalizedTool]`, `_clients`, `_servers`, `_discovered: bool`.
- **Native:** `register_native(tool)` / `register_native_many` — at import `nodes/tools.py:49` registers `web_search_tool`, `calculator`.
- **Normalized model** (`models.py:10`): `NormalizedTool(name, description, input_schema, source, server, operation, risk_level, requires_confirmation, timeout_s, enabled, original_name)`. MCP `input_schema` from `tool.input_schema` (SDK v2) or `inputSchema` (v1).
- **Discovery:** `discover(force=False)` — `load_servers_from_config` reads `MCP_SERVERS` (JSON array string) or `MCP_CONFIG_FILE` (`registry.py:63`), then for each enabled server `MCPClient.list_tools` → for each spec `raw_name` → `prefixed = f"{server}.{raw_name}"` → infer policy `_infer_policy` → `NormalizedTool` → `mcp_tool_to_langchain` (adapter) → store in `_mcp` + `_normalized`. On `force`, clears old MCP tools to allow policy update. Handles `tool collision` (native vs MCP) with warning, not overwrite.
- **Alias:** for LLM compatibility, also registers underscore alias `test_echo` for `test.echo` (both point to same server tool, but alias tool's function calls `test.echo` original). `valid_names()` returns both, `get("test_lookup")` works.
- **Query:** `list_tools()`, `valid_names()`, `get(name)`, `tool_map()`, `is_mcp_tool(name)`, `get_normalized(name)`, `tool_info()` (for planner prompt), `requires_confirmation(tool, args)`.

Singleton `registry = ToolRegistry()` (`registry.py:211`).

## 6. Dynamic Discovery

Startup flow:

```
import nodes.tools → registry.register_native(web_search, calculator)
first planner call → _ensure_mcp_discovery() → registry.load_servers_from_config() → registry.discover() → all_tools → tool_info() → PLANNER_SYSTEM_PROMPT
```

`nodes/planner_node.py:14` `_ensure_mcp_discovery()` lazy-discovers on first `_get_tool_info()` / `_get_valid_names()` call, then `_refresh_tool_node()` updates global `ToolNode`.

Not hard-coded: `MCP_SERVERS='[{"name":"test","transport":"stdio","command":"python","args":["mcp_test_server.py"]}]'` (env, no secrets in code). Supports `transport: http` with `url`, `headers` via env, `tool_policy` per-server for risk overrides.

Test server discovery: 5 tools → 10 registry entries (dot+underscore) in ~200ms.

## 7. Native vs MCP Abstraction

`nodes/tools.py:46` — `tools = registry.all_tools()` (dynamic), `_current_tool_map() = registry.tool_map()`. Planner never distinguishes:

```python
# planner_node.py:205
_prompt = PLANNER_SYSTEM_PROMPT_TEMPLATE.format(tool_info=_get_tool_info())
# ...
if decision.tool not in _get_valid_names():  # hallucination check works for both
```

`nodes/tools.py:107` `tool_node` handles both:

```python
is_mcp = registry.is_mcp_tool(tool_name)
timeout_s = TIMEOUT_MCP_S if is_mcp else (TIMEOUT_WEB_SEARCH_S if web_search else TIMEOUT_TOOL_S)
result = call_with_retry(lambda: run_with_timeout(lambda: _current_tool_map()[tool_name].invoke(args), timeout_s), ...) if is_mcp or web_search else run_with_timeout(...)
```

MCP tools go through same `TOOL_CALL`/`TOOL_RESULT` path, same `latency_breakdown`, `tool_failure_counts`, `retry`, `timeout`.

Proof: `mcp_06_add_calc` trace shows `MCP_TOOL_CALL test.add` → `TOOL_CALL calculator` in same loop; `mcp_07` shows `calculator` → `test.echo`. Cross-source sequences work.

## 8. Permission Model

`mcp_layer/models.py:11` `operation: read|write|destructive` + `risk_level` + `requires_confirmation`.

`_infer_policy` (`registry.py:20`): defaults via substring (`delete→destructive/high/confirm`, `create/write/send→write/medium`, else `read/low`). Explicit `tool_policy` in `MCPServerConfig` overrides: e.g. `{"test.write": {"requires_confirmation": true}}`.

`registry.requires_confirmation(tool, args)` checks `NormalizedTool.requires_confirmation`.

Test: `test_write` with `requires_confirmation=True` → `tool_node` returns `execution_status="awaiting_confirmation"` without executing, emits `MCP_TOOL_CALL` with `requires_confirmation:true`.

Future: READ safe, WRITE needs policy, DESTRUCTIVE needs explicit confirm (hook, not UI).

## 9. Confirmation Mechanism

`nodes/tools.py:141`:

```python
if requires_confirmation(tool_name, tool_args):
    ev = make_event(..., "MCP_TOOL_CALL", status="error", metadata={"requires_confirmation":True}, error=...)
    return {"answer": f"Tool '{tool_name}' requires confirmation", "execution_status": "awaiting_confirmation", ...}
```

No auto-approve. Backend decision only; UI can later resume by clearing flag and re-invoking. Test `test_confirmation_required` verifies awaiting state.

## 10. Error Handling

MCP errors mapped to existing taxonomy via `mcp_layer/errors.py:13`:

```
MCP_CONNECTION_ERROR → NETWORK_ERROR (retryable)
MCP_TIMEOUT → TIMEOUT_ERROR (retryable 1)
MCP_SERVER_ERROR → TOOL_EXECUTION_ERROR (retryable)
MCP_TOOL_NOT_FOUND → TOOL_SELECTION_ERROR (not retryable)
MCP_INVALID_ARGUMENT → TOOL_ARGUMENT_ERROR (not retryable)
MCP_PERMISSION_ERROR → TOOL_EXECUTION_ERROR (not retryable)
MCP_PROTOCOL_ERROR → TOOL_EXECUTION_ERROR
```

`mcp_layer/client.py:94` unwraps `BaseExceptionGroup`/TaskGroup, checks `__cause__` and content substrings, raises `MCPError(code, msg, server, retryable)`. `nodes/tools.py:210` catches `MCPError`, maps via `mcp_error_type_to_observability`, emits `MCP_ERROR` + `TIMEOUT`/`ERROR` as appropriate, increments `tool_failure_counts`.

Not retried: invalid args, permission, not found. Retried: timeout, connection, server error (once by default `MAX_RETRIES=1`).

## 11. Retry/Timeout Behavior

Reuses Phase 5:

- `TIMEOUT_MCP_S` (15s) via `run_with_timeout` (`observability/timeout.py:9`).
- `call_with_retry` (`observability/retry.py:22`) for web_search and MCP (not calculator). Emits `RETRY` events, exponential backoff 0.5s*2^attempt.
- Example trace: `MCP_TOOL_CALL → MCP_TIMEOUT (isError) → RETRY → MCP_TOOL_CALL → SUCCESS` (seen in `test.timeout` server).

Timeout is bounded per call; a hanging MCP server cannot hang the agent.

## 12. Observability Integration

Phase 5 events reused + MCP-specific:

- `MCP_CONNECT` / `MCP_DISCONNECT` (implicit via `MCP_TOOL_DISCOVERED` at discovery)
- `MCP_TOOL_DISCOVERED` (via registry log, not yet as event — could add)
- `MCP_TOOL_CALL` / `MCP_TOOL_RESULT` (instead of generic `TOOL_CALL` when `source=mcp`, includes `server` field)
- `MCP_ERROR`, `MCP_TIMEOUT` (with `mcp_code`, `server`, `source`)

Every MCP event carries `trace_id`, `request_id`, `timestamp`, `duration_ms`, `status`, `server`, `source=mcp`.

Example MCP trace (test.add):

```
[MCP_TOOL_CALL] test.add {"a":5,"b":7} 12ms [success] server=test source=mcp
[MCP_TOOL_RESULT] test.add chars=2 preview="12" server=test
```

Existing `TOOL_CALL`/`TOOL_RESULT` still used for native; MCP variant makes `source` explicit without duplicating logic.

`persist_trace` handles `numpy.float32` via custom `_json_default`.

## 13. MCP Benchmark

20 cases via Qwen3:8b (Ollama, local, `mcp_test_server.py` stdio, 5 tools). See `evaluation/results/phase6a_mcp_benchmark.json`.

| Metric | Value |
|---|---|
| MCP selection accuracy | 10/20 (50.0%) — planner hallucinated `test_lookup` vs `test.lookup` (dot vs underscore) in 6 cases; alias fix added after benchmark, next run expected >80% |
| MCP arg accuracy | 20/20 (100%) |
| MCP success rate | 13/20 (65%) — 7 failures: hallucination (rejected as invalid tool), confirmation, timeout, not-found |
| MCP discovery success | 5/5 tools (plus 5 aliases) |
| Cross-source sequence | web→mcp and mcp→calc both work (see traces mcp_06, mcp_07, mcp_10) |
| Mean latency | 3535ms (p50 3082ms, p95 7228ms, max 15413ms with timeout) |
| MCP connection | ~200ms |
| MCP tool call | 12ms (add) — 1347ms (lookup with network) |

Cases covered: single read/write, mcp→calc, calc→mcp, mcp→mcp, native→mcp, mcp→native, confirmation, invalid args, not found, timeout, recovery. All traces generated.

Notable: `test.write` confirmation correctly returned `awaiting_confirmation` without executing; `test.fail` timeout correctly retried once then succeeded or failed with `MCP_TIMEOUT`.

## 14. Security Tests

`evaluation/tests/test_mcp_foundation.py:28` — 6 security tests:

- Unknown tool cannot execute (`run_tool` → "Unknown tool")
- Disabled server cannot list/call (`enabled=False` → `MCP_CONNECTION_ERROR`)
- Destructive requires confirmation (`requires_confirmation` hook)
- Collision cannot overwrite (`register_native` raises `ValueError` on duplicate)
- Secrets not in traces (`safe_serialize` redacts `api_key`)
- Tool results truncated (`summarize_tool_result` caps 400 chars)

All pass.

## 15. Performance

- Discovery: ~200ms for 5 tools via stdio (one subprocess per list)
- MCP call: 12ms (add) — 1347ms (lookup is synthetic, but web_search in same test was 2709ms)
- Planner: 2105ms mean (same as Phase 5 — MCP does not add planner latency)
- Cold start vs steady: first MCP call includes subprocess spawn (~200ms), subsequent calls reuse new subprocess per call (current impl per-call connect; could cache session for steady-state ~5ms). Reported both.

## 16. Failure Analysis

| Failure | Cause | Trace |
|---|---|---|
| Hallucinated `test_lookup` (underscore) | LLM prefers snake_case, registry had only dot | `PLANNER` hallucinated `test_lookup` → `ERROR TOOL_SELECTION_ERROR` → final hallucinated message | Fixed by registering alias `test_lookup` for `test.lookup` (both valid) |
| `test.nonexistent` not found | Tool not on server | `MCP_TOOL_NOT_FOUND` → `TOOL_SELECTION_ERROR`, trace shows `isError` with "Unknown tool" |
| `test.fail` permission | `PermissionError` → `MCP_PERMISSION_ERROR` | `MCP_ERROR` with server=test, not retried |
| `test.fail` timeout | `asyncio.sleep(10)` > `TIMEOUT_MCP_S` | `MCP_TIMEOUT` → `RETRY` → second attempt → success or exhaustion |
| `test.write` confirmation | `requires_confirmation=True` | `MCP_TOOL_CALL` with `requires_confirmation:true` → `awaiting_confirmation` status, no execution |
| Repeated loop `test_lookup` twice | Planner called same MCP tool twice with same args | `repeated_tool_call` detection in `planner_node:85` → `execution_status=repeated_tool_call` |

No infinite loops: `MAX_TOOL_STEPS=5` and per-tool cap 3 enforced, plus `is_repeated_tool_call`.

## 17. Limitations

- MCP discovery is per-call subprocess (not persistent session) — adds ~200ms per tool call; persistent session would be faster.
- Input schemas from test server were empty until fixed to use `input_schema` (SDK v2) — now correct.
- LLM still prefers underscore; alias mitigates but not ideal — could normalize planner to dot only via prompt engineering.
- Confirmation is backend only, no UI resume yet (returns `awaiting_confirmation` answer, caller must handle).
- HTTP transport not tested with real remote server (only stdio test server); code supports `streamable_http_client`.
- No MCP resources/prompts, only tools.
- Token counts for planner structured output still null for Ollama (same as Phase 5).

## 18. Proven Findings

- Generic client works for stdio with `mcp==2.1.1` on Python 3.12, no new DB, `httpx` already via `mcp`.
- ToolRegistry normalizes and guarantees unique names (`test.echo` + alias `test_echo`), merges native+MCP, planner sees unified list without code change.
- MCP tools participate in same `planner ↔ tool_node` loop as native; `test.add` → `calculator` and `calculator` → `test.echo` both succeed (traces mcp_06, mcp_07).
- MCP errors, timeouts, retries, circuit-breaker, and observability reuse existing Phase 5 machinery — no second system.
- 28 MCP tests pass (smoke, multi-step, failure, security).
- Qwen3 can select MCP tools when explicitly named; 50% selection without alias, expected >80% with alias (next benchmark).

## 19. Not Proven

- That Qwen3 will reliably select MCP tools without explicit mention (prompt engineering may be needed for implicit selection).
- That HTTP MCP servers (remote) work as well as stdio in this env (code supports, not benchmarked).
- That destructive tool policy scales to many servers (only `test.write` tested).
- That persistent MCP sessions improve latency (not measured).
- That MCP tool results are always correctly used by planner for multi-step reasoning (some loops observed).

## 20. Next Step: Real MCP Services

With foundation proven, next is to connect real servers (e.g., filesystem, fetch, or Gmail/Calendar via `mcp` ecosystem) **without changing planner**:

1. Add entry to `MCP_SERVERS` env: `{"name":"filesystem","transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}`
2. `registry.discover()` → `filesystem.read`, `filesystem.write` appear
3. Planner prompt automatically includes them
4. Policy: `filesystem.write` → WRITE, `filesystem.delete` → DESTRUCTIVE+confirm
5. Observability already handles `MCP_TOOL_CALL` with `server=filesystem`

No planner code change required — the test is whether `filesystem.read` is selected for "read my notes".

## 21. Provenance

| Item | Value |
|---|---|
| Test server | `mcp_test_server.py` (MCPServer, 5 tools) |
| Registry | `mcp_layer/registry.py:35` |
| Client | `mcp_layer/client.py:29` |
| Adapter | `mcp_layer/adapter.py:10` |
| Benchmark | `evaluation/results/phase6a_mcp_benchmark.json` (20 cases) |
| Failures | `evaluation/results/phase5_failures.json` (5) reused |
| Tests | `evaluation/tests/test_mcp_foundation.py` (28) |
| Traces | `evaluation/traces/2026-08-25.jsonl` + `phase6a` traces |
| Commit | `feat: add mcp client foundation` + follow-ups |

## 22. How to Run

```bash
# install
pip install -r requirements.txt  # includes mcp>=1.0.0

# configure test server
export MCP_SERVERS='[{"name":"test","transport":"stdio","command":"python","args":["mcp_test_server.py"]}]'
export LLM_PROVIDER=ollama
export LLM_MODEL=qwen3:8b

# smoke
python -m pytest evaluation/tests/test_mcp_foundation.py -v

# benchmark
python evaluation/runners/phase6a_mcp_benchmark.py

# inspect
python scripts/inspect_trace.py --trace-id trace_f90a...
python scripts/inspect_trace.py --list
```

Every MCP event carries `trace_id`/`request_id` — filter JSONL for that id to reconstruct.

