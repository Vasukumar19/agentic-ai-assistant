# Phase 7 — Multi-Service Planning Depth Evaluation

Generated: 2026-08-26 | Model: qwen3:8b (Ollama, Q4_K_M, thinking disabled) | Dataset frozen (Phase 6C 60 cases) | Strategies: baseline / dependency / replan

## 1. Executive Summary

Three generic planning strategies were benchmarked against the identical frozen Phase 6C dataset to answer one question: **is the multi-server bottleneck planning depth, and does explicit dependency reasoning fix it?**

| Strategy | Tool sel. | Deps | 3-svc tool sel. | 3-svc deps | Completion | Loops | Latency mean/P95 | LLM calls/q |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| baseline | 73.3% | 21/31 (67.7%) | 30% | 41.7% | 75.0% | 18.3% | 9.8s / 21.2s | ~1.6 |
| dependency | **81.7%** | **25/31 (80.6%)** | 20% | 58.3% | 66.7% | **5.0%** | 12.1s / 17.2s | 3.27 |
| replan | 75.0% | 24/31 (77.4%) | **50%** | 66.7% | **75.0%** | 10.0% | 11.9s / **38.2s** | 4.83 |

**Answer: the bottleneck IS dependency reasoning, not tool selection** (1-service selection is 100% under every strategy). Explicit dependency planning fixes 2-service workflows (+10pp selection, +10.5pp deps, loops −13pp) but makes 3-service workflows *worse* (rigid plans exhaust MAX_TOOL_STEPS → 0% completion). Replan is the only strategy that improves 3-service selection (+20pp) at a heavy latency cost.

**Production recommendation: keep the baseline Planner as default. No strategy dominates. The dependency strategy's failure mode (premature termination 23.3%) and replan's P95 38s are disqualifying as unconditional defaults. A hybrid (replan only when ≥3 servers are involved) is the candidate for future evaluation.**

## 2. Phase 6C Baseline

Frozen byte-identical copy of the Phase 6C raw run: `evaluation/results/phase7_baseline_phase6c.json` (SHA-verified identical to `phase6c_multiserver_benchmark.json`). Dataset untouched.

## 3. Problem Definition

Phase 6C showed monotonic degradation: 1→100%, 2→80%, 3→30% tool selection; deps 67.7%. Hypotheses: (a) model cannot select tools, (b) model cannot reason about cross-server data dependencies. Phase 7 separates these by making dependencies explicit in three different ways and measuring.

## 4–5. Planning Strategies & Architecture

All strategies reuse the same Planner/Executor/Verifier graph, MCP layer, traces, and limits (`MAX_TOOL_STEPS=5`, retry/breakers). Selected via `PLANNING_STRATEGY` env — zero service-specific code anywhere.

| Strategy | Mechanism |
|---|---|
| baseline (A) | unchanged single-next-action planner (control) |
| dependency (B) | one structured `Plan` (goal/steps/depends_on/purpose, Pydantic) generated up-front; validated structurally; steps then executed deterministically in dependency-ready order **without per-step LLM calls**; `{step_id}` placeholders substituted from prior results; repair loop (≤2) on validation errors; final answer composed once from step results |
| replan (C) | baseline loop but prompt explicitly exposes Remaining Goal / Completed Steps / Available State / Failed Steps each turn |

New module: `planning/` (schema.py, validation.py). Planner integration: `nodes/planner_node.py` (`_dependency_planner`, replan prompt block).

## 6. Dependency Representation

```json
{"goal": "...", "steps": [
  {"id": "s1", "tool": "calendar.create_event", "arguments": {...}, "depends_on": [], "purpose": "..."},
  {"id": "s2", "tool": "reminders.create", "depends_on": ["s1"], ...}], "completion_conditions": "..."}
```

## 7. Plan Validation

Pre-execution checks (`planning/validation.py`): unknown tools, duplicate ids, missing/self/circular dependencies (Kahn), confirmation-gated ops flagged before execution. Invalid → error fed back for ≤2 repair rounds → honest failure, never executed blind.

## 8. Execution & 9. State Propagation

Dependency strategy executes only dependency-ready steps sequentially (no parallelism added). Results stored per step id; `{s1}`-style placeholders resolved from prior outputs. Measured dependency-data flow via ordered edge satisfaction (§11 below).

## 10. Benchmark Design

Same 60-case frozen dataset for all strategies. Runner: `phase7_strategy_benchmark.py` (env-selected strategy). Evaluator: `phase7_evaluate.py` — identical scoring logic across strategies; results in `phase7_strategy_comparison.json`. Raw runs preserved separately per strategy. Benchmark wording/case IDs never enter planner prompts.

## 11. Results

See table in §1. Notable secondary numbers:

- **Dependency strategy**: repeats exploded to 66 total (vs 15) because rigid re-execution hits the same failing step until loop detection; but genuine *tool loops* dropped 18.3%→5.0%.
- **Replan**: best exact-sequence accuracy (51.7%) and best completion tie (75%) with baseline.
- Baseline `avg_llm_calls` shows 0 due to structured-output usage not being token-tracked (known Phase 5 limitation); dependency/replan counts come from `llm_usage` instrumentation of direct invokes (plan generation + final compose; guard re-prompts).

### Planning-Quality Metrics (dependency strategy)

| Metric | Value |
|---|---:|
| Plans created | 60 |
| Valid on first attempt | 55 (91.7%) |
| Repaired within ≤2 rounds | 3 |
| Invalid Plan Rate (final) | 3.3% (honest abort) |
| Circular Dependency Rate | 0% |
| Plan Revision Rate | 8.3% |

## 12–14. Scale Results (tool selection / dependency / completion)

| Services | baseline | dependency | replan |
|---|---|---|---|
| 1 | 100% / — / 100% | 100% / — / 100% | 100% / — / 90% |
| 2 | 80% / 84.2% / 70% | **90% / 94.7%** / 73.3% | 80% / 84.2% / 73.3% |
| 3 | 30% / 41.7% / 50% | 20% / 58.3% / **0%** | **50% / 66.7%** / 50% |

The key graphs: dependency accuracy rises with explicit planning at every scale, but *completion* collapses for dependency-strategy at 3 services (23.3% overall premature termination — plans longer than MAX_TOOL_STEPS=5 or stuck on a failed step with no fallback budget left).

## 15. Strategy Comparison

- **Selection**: dependency > baseline ≈ replan overall; replan wins at 3 services by a wide margin.
- **Sequences**: replan > baseline >> dependency (dependency's deterministic execution doesn't optimize order beyond its declared DAG).
- **Recovery**: replan best by construction (failed steps re-exposed every turn); dependency worst (single rigid plan).
- **Cost**: dependency ≈ +23% mean latency; replan ≈ +21% mean but P95 nearly doubles (38.2s) from repeated full-prompt turns.

## 16. Failure Analysis (primary categories)

| Category | baseline | dependency | replan |
|---|---:|---:|---:|
| MODEL_PLANNING_FAILURE (3-svc incomplete) | dominant | dominant | reduced |
| PREMATURE_TERMINATION | 3.3% | 23.3% | 6.7% |
| REPEATED_TOOL (loop status) | 18.3% | 5.0% | 10.0% |
| MCP_FAILURE | 0 | 0 | 0 |
| INFRASTRUCTURE_FAILURE | 0 | 0 | 0 |
| EVALUATOR_FAILURE | negative-probe subset (~7 cases) identical across strategies | | |

Per-failure records with expected-vs-actual dependencies and trace_ids preserved in per-strategy raw JSONs.

## 17. Latency Analysis

Normal vs extra-call groups and per-scale latencies in `phase7_strategy_comparison.json`. Better planning costs real time: dependency adds ≈+2.3s mean; replan's tail (P95 38s) comes from 4.83 LLM round-trips/query at ~2–4s each.

## 18. LLM Cost/Call Analysis

LLM calls/query: baseline ~1.6 (uninstrumented lower bound) · dependency 3.27 · replan 4.83. Dependency shifts spend from per-step decisions to one plan + one compose; replan pays per turn. Tokens/sec unchanged (~74 tps when measured).

## 19. Security/Confirmation

Confirmation gating untouched and active in all strategies; dependency strategy additionally flags gated ops at *validation* time (before any execution). Injection probes behaved identically across strategies (no destructive action from note content).

## 20. Proven Findings

1. Degradation cause = dependency reasoning depth, not tool selection (1-service 100% everywhere).
2. Explicit dependency planning significantly improves 2-service workflows (selection +10pp, deps +10.5pp, loops −13pp).
3. Rigid full-plan execution fails at 3 services (completion 0%) — plans exceed step budgets and can't adapt.
4. Replanning with explicit state is the only strategy that lifts 3-service selection (30%→50%) and deps (41.7%→66.7%).
5. Plan quality is high (91.7% first-pass valid, 0 cycles) — schema-guided decomposition works; execution adaptivity is the gap.
6. All gains cost latency: no free lunch (dep +23% mean; replan P95 ×1.8).

## 21. Not Proven

- That any strategy justifies replacing the production default (none dominates all five axes).
- That a hybrid (strategy selected by service count) would work — proposed, not tested.
- Parallel independent-step execution (explicitly out of scope).
- Token-level cost comparison for baseline (structured-output usage not exposed by provider path).

## 22. Limitations

n=60 shared dataset; single model (qwen3:8b); MAX_PLAN_STEPS=6/MAX_TOOL_STEPS=5 interact strongly with dependency strategy; llm_usage instrumentation asymmetry between strategies; evaluator negative-probe subset affects all strategies equally but inflates absolute "failure" rates.

## 23. Recommended Planner Strategy

**Keep baseline as production default today.** For 3-server workflows specifically, replan is the best available strategy (only one to beat 50% selection) despite P95 38s — acceptable for async/background productivity tasks, not for interactive chat. Proposed follow-up experiment (Phase 7B): conditional strategy — replan when ≥3 servers implicated, baseline otherwise — measured on the same dataset before any default change.

## 24. Next Phase

Phase 8 candidates: (a) hybrid strategy validation, (b) raise MAX_PLAN_STEPS/MAX_TOOL_STEPS interaction study for dependency mode with mid-plan fallback, (c) only after planning depth ≥3-services exceeds ~70% completion: begin external service integration.

## Comparison Table (required single view)

| Metric | Baseline | Dependency | Replan |
|---|---:|---:|---:|
| Server selection | 75.0% | **85.0%** | 80.0% |
| Tool selection | 73.3% | **81.7%** | 75.0% |
| Dependency accuracy | 67.7% | **80.6%** | 77.4% |
| Exact sequence | 46.7% | 16.7% | **51.7%** |
| Acceptable sequence | 46.7% | 16.7% | **53.3%** |
| Task completion | **75.0%** | 66.7% | **75.0%** |
| Premature termination | 3.3% | 23.3% | 6.7% |
| Tool-loop rate | 18.3% | 5.0% | 10.0% |
| Repeated calls | 15 | 66 | 12 |
| Mean latency | **9819ms** | 12085ms | 11926ms |
| P95 latency | 21161ms | **17245ms** | 38151ms |
| LLM calls/query | ~1.6* | 3.27 | 4.83 |
| 3-svc tool selection | 30% | 20% | **50%** |
