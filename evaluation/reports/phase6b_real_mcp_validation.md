
# Execution Efficiency Audit (Phase 6B.1)

Measurement-only audit of the 30-case real MCP benchmark. No Planner, MCP architecture, benchmark queries, expected sequences, or scoring rules were modified. Raw benchmark (`phase6b_real_mcp_benchmark.json`) remains immutable; all derived metrics live in `phase6b_efficiency_audit.json`.

## Capability vs Efficiency

These are **independent** dimensions and must not be conflated:

| Dimension | Measures | Phase 6B result |
|---|---|---|
| Capability | tool selection, argument validity, successful execution | 30/30 selection, 30/30 args, 30/30 success |
| Efficiency | exact sequence, repeated calls, extra calls, latency overhead | 16.7% raw exact, 76.7% canonical exact, 0.808 efficiency |

**100% tool selection does NOT imply 100% efficient execution.** "Task completed successfully" does NOT imply "no unnecessary tool calls occurred." The agent reliably picks the right capability, but in 7 of 30 cases it did more work than the task required.

## Canonical Tool Naming

Qwen3 emits both naming variants for MCP tools:

```
filesystem_read_file  ->  filesystem.read_file   (canonical)
filesystem_write_file ->  filesystem.write_file
filesystem_list_directory -> filesystem.list_directory
filesystem_get_file_info -> filesystem.get_file_info
filesystem_list_allowed_directories -> filesystem.list_allowed_directories
```

Canonicalization is required for fair sequence evaluation because the alias and the canonical name are the *same capability* — counting them as different tools would understate sequence accuracy. This is an **evaluation-layer-only** operation: execution traces preserve the actual invoked name (e.g. `filesystem_read_file`), and canonicalization maps it for analysis without rewriting history.

- Raw (as-executed) exact sequence accuracy: **5/30 = 16.7%**
- Canonicalized exact sequence accuracy: **23/30 = 76.7%**

The 60pp gap is almost entirely a naming-representation artifact, not an agent behavior difference.

## Repeated Tool Calls

**5/30 cases (16.7%) contained repeats; 7 redundant calls total.**

| Case | Expected | Raw executed | Canonical | Classification |
|---|---|---|---|---|
| real_05 | `list_allowed_directories` ×1 | dot, underscore, dot | same tool ×3 | MODEL_FAILURE (alias churn + re-verify) — repeated 2 |
| real_10 | `list_directory`, `calculator` | list → calc → list | list ×2 | SEQUENCE_FAILURE — second `list_directory` after calc is redundant |
| real_11 | `read_file` ×1 | list → read (read failed: guessed filename) | extra `list_directory` | Legitimate dependency — planner explored before reading; first read hit FileNotFoundError. Classified SEMANTICALLY_AMBIGUOUS leaning legitimate |
| real_13 | `read_file` ×1 | read → calc → read | read ×2, extra calculator | SEMANTICALLY_AMBIGUOUS — query asked for sum of two files' values; single-read expectation was arguably underspecified (evaluator note) |
| real_15 | `list`, `calculator` | list → calc → list → calc | each ×2 | SEQUENCE_FAILURE — full duplicate cycle; likely verification behavior |
| real_24 | `write_file` ×1 | write → write | write ×2 | MODEL_FAILURE — retried after first attempt already succeeded (result interpretation) |
| real_27 | `read_file` ×1 | read → calculator | extra calculator | Legitimate — query said "add 10 and 20"; calculator call was task-required, evaluator expectation was too narrow (EVALUATOR_FAILURE) |

Not every extra call is incorrect: real_11 (explore-then-read), real_13/real_27 (task actually needed more than the declared expectation) are defensible. Unambiguous waste: real_05 (×2), real_10, real_15 (×2), real_24.

## Tool Call Efficiency

Formula:

```
efficiency = total_expected_calls / total_actual_calls
extra_per_task = (actual − expected) / n_cases
```

| Metric | Value |
|---|---|
| Expected calls/task | 1.40 |
| Actual calls/task | 1.73 |
| Extra calls/task | +0.33 |
| **Efficiency** | **0.808** (80.8% of tool invocations were strictly required) |

## Latency Impact

| Group | Mean | P50 | P95 | n |
|---|---|---|---|---|
| Normal (no extra calls) | 4120 ms | 3989 ms | 5948 ms | 23 |
| Extra-call cases | 6828 ms | 6347 ms | 11754 ms | 7 |
| **Difference** | **+2708 ms mean** | | | |

The increase is *associated with* additional planner/tool cycles (each redundant cycle costs one planner LLM round-trip plus tool execution). Traces support correlation, not proven causality — extra-call cases also skew toward harder multi-step tasks (real_11, real_13, real_15), which independently raise latency. Redundant-cycle cost is bounded by existing protections (`MAX_TOOL_STEPS=5`, per-tool failure cap 3, repeat-call loop detection).

## Phase 6A vs Phase 6B

| Metric | Phase 6A (test server) | Phase 6B (real filesystem) |
|---|---|---|
| Tool selection (raw) | 50% → 40% post-rerun (dot-vs-underscore hallucination rejected as invalid) | 100% (alias accepted by registry) |
| Argument accuracy | 100% | 100% |
| Tool success | 65% | 100% |
| Exact sequence (raw) | not measured | 16.7% |
| Canonical sequence | not measured (aliases added post-benchmark) | 76.7% |
| Repeated-call rate | observed (real_17-style loops) but unmeasured | 16.7% of cases, 7 calls |
| Expected calls/task | — | 1.40 |
| Actual calls/task | — | 1.73 |
| Efficiency | — | 0.808 |
| Mean latency | 3535 ms | 4752 ms |
| P95 latency | 7228 ms | 7842 ms |

The Phase 6A naming problem: Qwen3 generated snake_case (`test_lookup`) while the registry exposed only dotted names (`test.lookup`); validation rejected them as invalid tools, producing hard failures. Phase 6B's registry accepts both forms (alias resolves to canonical at execution time), converting those failures into successes — but the efficiency audit shows the underlying naming instability persists as *redundant* work rather than errors (e.g., real_05 alternated both spellings within one request).

## Qwen3 Comparison (vs Phase 3/3B)

| Metric | Phase 3B (native only) | Phase 6B (MCP) |
|---|---|---|
| Tool selection | 93.3% | 100% (explicit-tool queries) |
| Sequence accuracy | 76.7% exact | 16.7% raw / 76.7% canonical |
| Premature stop | 13.3% | ~3% (1 loop-detection termination across 30) |
| Repeated-loop rate | 3.3% flagged | 16.7% of cases had repeats (softer: mostly completed anyway) |
| Avg tool calls/query | 1.43 | 1.73 |
| Mean latency | 5600 ms | 4752 ms |

MCP did not degrade core orchestration: selection and completion improved, latency is comparable or better than 3B. The new failure mode is redundancy (extra cycles), not wrong-tool or no-tool failures.

## Failure Analysis

Primary classification per imperfect case (capability was 30/30; classifications concern sequence/efficiency):

| Category | Count | Cases |
|---|---|---|
| EVALUATOR_FAILURE | 2 | real_13, real_27 (expectations narrower than the actual task wording; agent behavior defensible) |
| MODEL_FAILURE | 2 | real_05 (alias churn + re-verification), real_24 (redundant re-write after success) |
| SEQUENCE_FAILURE | 2 | real_10, real_15 (duplicate cycle after completion point) |
| SEMANTICALLY_AMBIGUOUS (leaning legitimate) | 1 | real_11 (explore-before-read after FileNotFoundError) |
| All others (TOOL_SELECTION / ARGUMENT / PREMATURE / POLICY / CONFIRMATION / VERIFICATION / MCP_SERVER / MCP_PROTOCOL / TIMEOUT / NETWORK / INFRASTRUCTURE) | 0 | — |

No case failed on capability. No MCP server, protocol, timeout, network, or infrastructure failures occurred in the 30-case run.
