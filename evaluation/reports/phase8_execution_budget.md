# Phase 8 — Execution Budget Evaluation

**Question:** How much execution budget does the agent actually need for legitimate long-horizon workflows, and what is the safest quality/latency tradeoff?

**Date:** 2026-08-26 · **Model:** qwen3:8b (Ollama, reasoning off) · **Dataset:** frozen Phase 6C 60-case multi-server set · **Strategy:** hybrid (classifier + dependency + replan)

---

## 1. Executive Summary

Phase 7B found the hybrid planner tripled 3-server tool selection (30%→90%) but completion collapsed to 42.4%. The working hypothesis was that correct plans exceeded `MAX_TOOL_STEPS=5`. Phase 8 decoupled execution budget from loop protection (`MAX_EXECUTION_STEPS`), added state-aware alternating-loop detection, and measured budgets 5/7/10/15.

**Findings:**
1. Raising the budget recovers real completion: **42.4% → 60.3%** at budget 10 (+17.9pp). At budget 5, **35.6% of hybrid runs were step-cap terminated** (hidden inside "premature termination" until traces were re-examined).
2. Completion plateaus at **budget 10**; budget 15 adds nothing (+redundant calls, 3× mean latency tail).
3. Budget is necessary but not sufficient: even at 10–15, ~28% of runs terminate prematurely — a planner failure mode (never reaching `final`), not a budget failure.
4. Loop protection remains fully effective at every budget (loop rate ≤3.4%; identical/alternating loops still terminated).
5. Recommended default: **MAX_EXECUTION_STEPS=10** with the hybrid strategy.

## 2. Phase 7B Root Cause (Revised)

Phase 7B attributed the hybrid completion collapse to plans exceeding 5 steps. Phase 8 confirms this partially:

- At budget 5, 21 of 27 non-terminal runs ended at ≥5 planner steps → true step-cap terminations (**35.6%** of executed cases). The old runner labeled these merely "running"; they were indistinguishable from other premature exits without trace forensics.
- However, budgets 7–15 reveal a second failure mode that budget cannot fix: repeated failing tool calls (caught by per-tool failure breakers) and plans that never reach a final answer (~21–28% premature at all budgets ≥7).

So the collapse had **two causes**: step-cap truncation (fixable by budget) and planner non-convergence (not fixable by budget).

## 3. Execution Budget Architecture

- `config.MAX_EXECUTION_STEPS` (env-overridable; defaults to `MAX_TOOL_STEPS=5` for backward compatibility) is the legitimate-workflow budget enforced in `graph.should_continue`.
- On exhaustion the router emits a structured ERROR event (`termination_reason=budget_exhausted`, `execution_step`, `execution_budget`, `remaining_budget`, `loop_detected`, `circuit_breaker=execution_budget`) and routes to END.
- `save_history_node` recomputes terminal status (routers cannot persist LangGraph state) and **returns** `execution_status` so `completed` vs `budget_exhausted` vs `running` is distinguishable downstream.
- Per-tool failure circuit breaker (`MAX_TOOL_FAILURES_PER_TOOL=3`) is unchanged and independent of the budget.

**Bug found during evaluation:** the first implementation computed but did not *return* `execution_status` from `save_history_node`; LangGraph silently dropped it, so benchmarks recorded `running` where traces showed `budget_exhausted`. Fixed + regression test added; all four result files were label-corrected from persisted trace evidence (see §6).

## 4. Loop Protection Architecture

- Consecutive-identical detection (existing): same tool+args as last execution.
- New state-aware `detect_loop` (`nodes/planner_node.py`): maintains `(tool,args)`-signature history with truncated results in `state.tool_call_history`. A signature seen **twice+ with unchanged results** terminates (`alternating_identical`) — catches A→B→A→B cycles. State-changing repeats (e.g., write after read-back) are allowed; failed calls allow one corrected retry.
- Verified independent of budget by tests: raising `MAX_EXECUTION_STEPS` does not weaken any breaker.

## 5. Experimental Setup

- Frozen dataset: `evaluation/datasets/phase6c_multiserver.json` (60 cases: 10 single-server, 30 two-service, 10 three-server; expected tools, dependency edges, acceptable variants untouched).
- Runner: `evaluation/runners/budget_benchmark.py --budget N [--resume]` — persists a per-case checkpoint after every case (survives crashes; used twice during b15).
- Evaluator: `evaluation/runners/budget_evaluate.py` (same scoring rules as Phase 7; adds `budget_exhausted` status accounting).
- Real MCP servers (calendar/notes/reminders), local Ollama, no cloud APIs, no prompt changes, no scoring changes.

## 6. Label Correction Methodology

Benchmark statuses in b5 (Phase 7B run) and initially in b7/b10/b15 mislabeled some terminations as `running` because of the §3 persistence bug (and, for b5, because the pre-Phase-8 runner never recorded terminal status at all).

Correction: each case's persisted trace (`evaluation/traces/*.jsonl`) contains `FINAL_ANSWER.metadata.execution_status` (post-fix runs) or `FINAL_ANSWER.metadata.planner_steps` (b5: rule `status==running AND planner_steps>=5 → budget_exhausted`). Corrections applied by script, marked `"status_backfilled_from_trace": true` per record; behavior fields (called sequences, latencies) were never modified. Corrected counts: b5: 21, b7: 12, b10: 6, b15: 6.

## 7–10. Results

### Overall comparison (hybrid strategy, n = executed cases)

| Metric | B5 | B7 | B10 | B15 |
|---|---:|---:|---:|---:|
| n (executed / infra-fail) | 59 / 1 | 57 / 3 | 58 / 2 | 57 / 3 |
| Server selection % | 79.7 | 84.2 | 86.2 | 82.5 |
| Tool selection % | 79.7 | 82.5 | **82.8** | 80.7 |
| Dependency accuracy % | 76.7 | **82.8** | 79.3 | 79.3 |
| **Task completion %** | 42.4 | 52.6 | **60.3** | 57.9 |
| Premature termination % | 10.2 | 21.1 | 27.6 | 28.1 |
| Tool-loop rate % | 3.4 | 1.8 | 1.7 | 1.8 |
| **Budget exhaustion %** | **35.6** | 17.5 | 6.9 | 7.0 |
| Cases w/ redundant calls | 34 | 35 | 36 | 37 |
| Total redundant calls | 55 | 84 | 110 | 136 |
| Mean latency ms | 15,006 | 19,354 | 19,120 | **56,021** |
| P50 latency ms | 15,125 | 16,359 | 18,048 | 18,158 |
| P95 latency ms | 31,376 | 51,445 | 37,420 | 44,717 |
| Avg LLM calls/query | 2.58 | 2.56 | 2.62 | 2.61 |

### By service count — completion %

| Budget | 1-server (n=10) | 2-service (n≈28) | 3-server (n=10) |
|---|---:|---:|---:|
| 5 | 70.0 | 27.6 | 20.0 |
| 7 | 60.0 | 51.9 | 10.0 |
| 10 | 70.0 | 53.6 | **40.0** |
| 15 | 70.0 | 48.1 | 40.0 |

3-server completion doubles from 20%→40% between budget 5 and 10 — direct evidence that legitimate long-horizon workflows were being truncated. (b7's 10% is small-sample noise; its 3-server tool selection was 100%.)

### Final canonical table

| Budget | Selection % | Dependency % | Completion % | Efficiency¹ | Mean ms | P95 ms | LLM calls | Loop rate % | Budget exhaustion % |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 79.7 | 76.7 | 42.4 | 0.87 | 15,006 | 31,376 | 2.58 | 3.4 | 35.6 |
| 7 | 82.5 | 82.8 | 52.6 | 0.68 | 19,354 | 51,445 | 2.56 | 1.8 | 17.5 |
| 10 | 82.8 | 79.3 | 60.3 | 0.62 | 19,120 | 37,420 | 2.62 | 1.7 | 6.9 |
| 15 | 80.7 | 79.3 | 57.9 | 0.57 | 56,021 | 44,717 | 2.61 | 1.8 | 7.0 |

¹ call efficiency = expected calls ÷ actual calls per task (lower = more redundancy).

## 11. Completion Analysis

- b5→b10: +17.9pp overall (SE ≈ ±6.4pp at n≈58 — significant, >2 SE). Driven by un-truncating 2- and 3-service workflows.
- b10→b15: −2.4pp — within noise; no improvement. Plateau reached at 10.
- Remaining ~40% non-completion splits into planner non-convergence (~28%) plus infra/timeout/loop singles.

## 12. Loop Safety

Loop rate stays ≤1.8% at budgets 7–15 (vs 18.3% for the baseline strategy on the same dataset). Exactly one `repeated_tool_call` termination per run confirms the breaker still fires when genuinely needed. Safety tests verify: identical-repeat terminates, A→B→A→B terminates, failed-then-corrected-retry allowed, state-changing repeats allowed, confirmation blocking independent of budget, per-tool breaker unchanged. **Raising the budget did not weaken protection.**

## 13. Redundant Calls

Monotonic growth: 55 → 84 → 110 → 136 (b5→b15). Extra budget is spent predominantly re-attempting failing calls rather than progressing plans. This is the cost side of the tradeoff and the strongest argument against budget 15.

## 14. Latency

Mean is flat b7→b10 (~19s) then triples at b15 (56s), caused by outlier wandering (worst case: 232s in a 3-server task that cycled list/get calls until breakers fired). P50 grows mildly (15.1→18.2s). P95 is noisy (31→51→37→45s); b7's spike includes model-load outliers. No latency argument exists for 15; b10 matches b7's mean with better completion.

## 15. LLM Usage

Flat across budgets (2.56–2.62 calls/query) — planner convergence attempts don't increase with budget; the extra executions come from longer dependency-plan fan-out within the same planner invocations.

## 16. Failure Classification (Budget 10)

| Class | Share | Notes |
|---|---:|---|
| Completed | 60.3% | |
| PLANNER_FAILURE (premature/non-convergence) | 27.6% | plan never reaches final; often repeated failing MCP calls until per-tool breaker stops them |
| BUDGET_TOO_LOW | 6.9% | down from 35.6% at b5 |
| Infrastructure failures | 2 cases | MCP TaskGroup errors |
| Timeouts | 2 cases | planner timeouts |
| Loop terminations | 1 case | correct behavior |
| Awaited confirmation | 0 | none required by dataset writes under hybrid |

**BUDGET_TOO_LOW vs PLANNER_FAILURE:** 21:15 at b5 → 4:16 at b10. Budget fixes the minority it can; the residual majority is planner quality.

## 17. Security / Confirmation

Unchanged and verified by tests: sandboxed filesystem server denies path traversal; injection probes (p6c_52/54/57/60) correctly refused or executed read-only paths at all budgets; confirmation gating precedes dispatch regardless of remaining budget.

## 18. Regression

Final full suite: **188 passed, 0 failed, 0 skipped** (`python -m pytest evaluation/tests/ -q`, 189s).

Two test-infrastructure defects were found and fixed en route (no production code weakened):
1. `save_history_node` did not return `execution_status` (§3) — fix + 2 regression tests (suite now 188 incl. new budget tests).
2. `test_llm_call_counters.py` set `MOCK_LLM=1` at import, permanently caching MockLLM into the session singleton and poisoning the 5 memory-agent tests with canned answers ("task complete."). Replaced with patch-and-restore fixture scoped to that module only. Root-caused via bisection (pairwise runs); both files now pass in isolation and together and in full-suite order.

## 19. Proven Findings

1. Step-cap truncation caused 35.6% of hybrid failures at budget 5; raising the budget to 10 recovers +17.9pp completion (statistically significant).
2. Completion plateaus at budget 10; 15 provides no measurable gain.
3. Redundant calls grow monotonically with budget (55→136).
4. Mean latency explodes at 15 (3×) via outlier wandering; flat 7→10.
5. Loop/confirmation/per-tool-breaker safety is invariant to budget.
6. Residual ~28% premature termination at high budgets is planner non-convergence, unreachable by budget alone.

## 20. Not Proven

- b10 vs b15 completion difference (−2.4pp) is within noise (n≈57; SE ≈6.5pp) — cannot claim 10 strictly better on completion, only on latency/redundancy.
- b7's 3-server completion dip (10%) — small-sample artifact suspected but unproven.
- Whether planner non-convergence responds to prompting/context changes (deliberately not tested here — no prompt modifications allowed).
- Single-run variance: one run per budget; day-to-day Ollama drift unquantified.

## 21. Production Recommendation

Adopt **MAX_EXECUTION_STEPS=10** (with the hybrid planner for multi-server work):
- Best completion (60.3%), mean latency equal to b7, P95 below b7 and b15,
- Budget exhaustion rare (6.9%) so the cap acts as a backstop, not a routine terminator,
- Loop protection intact.

Keep 5 only for latency-critical deployments whose workflows are known shallow (single-server Q&A completes equally well at any budget). Do **not** adopt 15: strictly dominated (same completion as 10 within noise, 3× mean latency, 2.5× redundancy vs b5). If no budget clearly dominates for a given deployment profile, retain 5 as safe default and gate higher budgets behind workflow-depth needs — for this system's measured profile, 10 dominates.

## 22. Phase 9 Recommendation

Attack the residual planner non-convergence (~28%), which no budget can fix:
1. Adaptive budget by classifier level (SIMPLE=5, MULTI_STEP=10) instead of global constant.
2. Plan-time feasibility check: reject plans whose step count exceeds remaining budget and force decomposition.
3. Failure-aware replanning: after 2 consecutive failures of the same tool, require the planner to change arguments or skip the step explicitly (currently the per-tool breaker hard-stops mid-plan without a final answer).
4. Then Gmail/OAuth MCP integration (original Phase 9 scope) once completion is stabilized.

---

*Artifacts:* results `evaluation/results/phase8_hybrid_budget{7,10,15}_results.json`, corrected baseline `phase7_hybrid_cap2_rep1_results.json`, runner `evaluation/runners/budget_benchmark.py`, evaluator `evaluation/runners/budget_evaluate.py`, safety tests `evaluation/tests/test_execution_budget.py` (15).
