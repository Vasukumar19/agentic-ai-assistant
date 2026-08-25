# Phase 3B — Planner Reliability, Completion Guards & Latency Report

**Generated**: 2026-08-25T10:00:53Z
**Execution Mode**: REAL LLM
**Model**: gemini-3.6-flash
**Dataset**: `evaluation/datasets/phase3b_reliability.json` (30 completed, 0 rate limited)

## 1. Before vs After Comparison

| Metric | Phase 3 Baseline (ReAct) | Phase 3 Initial Planner | Phase 3B Reliability Planner | Δ (vs Phase 3 Initial) |
|---|---:|---:|---:|---:|
| **Tool Selection Accuracy** | 24.0% | 44.0% (Mock) / 40.0% (Real) | **93.3%** | +49.3pp |
| **Tool Sequence Accuracy** | 20.0% | 40.0% (Mock) / 40.0% (Real) | **76.7%** | +36.7pp |
| **Multi-Step Completion** | 20.0% | 40.0% (Mock) / 33.3% (Real) | **70.0%** | +30.0pp |
| **Completion Guard Accuracy** | — | — | **76.7%** | NEW |
| **Final Before Required Tool Rate** | 24.0% | 16.0% (Mock) / 20.0% (Real) | **13.3%** | -2.7pp |
| **Missing Tool Rate** | 36.0% | 12.0% (Mock) / 40.0% (Real) | **3.3%** | -8.7pp |
| **Premature Stop Rate** | 24.0% | 16.0% (Mock) / 20.0% (Real) | **3.3%** | -12.7pp |
| **Tool Loop Rate** | — | — | **3.3%** | 0.0% |
| **Tool Argument Accuracy** | — | 100.0% | **100.0%** | 0.0pp |
| **Mean Latency** | 0.84s (Mock) / 6.60s (Real) | 1.56s (Mock) / 27.18s (Real) | **5.60s** | — |
| **P95 Latency** | 1.20s (Mock) / 19.18s (Real) | 2.10s (Mock) / 41.43s (Real) | **10.94s** | — |
| **Avg LLM Calls / Query** | 1.0 | 1.6 (Mock) / 1.2 (Real) | **3.4** | — |
| **Avg Tool Calls / Query** | 0.5 | 0.8 (Mock) / 0.6 (Real) | **1.4** | — |

## 2. Latency & LLM Call Breakdown

- **Mean Total Latency**: `5.60s`
- **Mean Planner LLM Processing Time**: `3.09s`
- **Average Planner Invocations per Query**: `2.43`
- **Average Total LLM Calls per Query**: `3.43`
- **Average Tool Calls per Query**: `1.43`

## 3. Performance by Target Category

| Category | Total Cases | Sequence Accuracy | Guard Accuracy | Missing Tool Rate | Premature Stop Rate |
|---|---:|---:|---:|---:|---:|
| `tool_necessity` | 10 | 90.0% | 90.0% | 10.0% | 0.0% |
| `premature_termination` | 10 | 100.0% | 100.0% | 0.0% | 0.0% |
| `multistep_dependency` | 10 | 40.0% | 40.0% | 0.0% | 10.0% |

## 4. Per-Case Execution Traces

| Case ID | Category | Expected Sequence | Actual Sequence | Result | Failure Mode | Latency | LLM Calls |
|---|---|---|---|---|---|---:|---:|
| p3b_nec_001 | tool_necessity | `calculator` | `calculator` | ✅ PASS | none | 7.22s | 3 |
| p3b_nec_002 | tool_necessity | `calculator` | `calculator` | ✅ PASS | none | 2.22s | 3 |
| p3b_nec_003 | tool_necessity | `calculator` | `calculator` | ✅ PASS | none | 1.78s | 3 |
| p3b_nec_004 | tool_necessity | `web_search` | `web_search` | ✅ PASS | none | 4.54s | 3 |
| p3b_nec_005 | tool_necessity | `web_search` | `web_search` | ✅ PASS | none | 7.92s | 3 |
| p3b_nec_006 | tool_necessity | `rag` | `rag` | ✅ PASS | none | 3.99s | 2 |
| p3b_nec_007 | tool_necessity | `rag` | `rag` | ✅ PASS | none | 1.53s | 2 |
| p3b_nec_008 | tool_necessity | `rag` | `rag` | ✅ PASS | none | 1.79s | 2 |
| p3b_nec_009 | tool_necessity | `web_search` | `[]` | ❌ FAIL | missing_tool | 0.98s | 2 |
| p3b_nec_010 | tool_necessity | `rag` | `rag` | ✅ PASS | none | 1.45s | 2 |
| p3b_prem_001 | premature_termination | `web_search, calculator` | `web_search, calculator` | ✅ PASS | none | 6.70s | 4 |
| p3b_prem_002 | premature_termination | `rag, calculator` | `rag, calculator` | ✅ PASS | none | 3.84s | 3 |
| p3b_prem_003 | premature_termination | `rag, calculator` | `rag, calculator` | ✅ PASS | none | 3.51s | 3 |
| p3b_prem_004 | premature_termination | `web_search, calculator` | `web_search, calculator` | ✅ PASS | none | 5.71s | 4 |
| p3b_prem_005 | premature_termination | `web_search, calculator` | `web_search, calculator` | ✅ PASS | none | 6.80s | 4 |
| p3b_prem_006 | premature_termination | `rag, calculator` | `rag, calculator` | ✅ PASS | none | 2.65s | 3 |
| p3b_prem_007 | premature_termination | `web_search, calculator` | `web_search, calculator` | ✅ PASS | none | 6.03s | 4 |
| p3b_prem_008 | premature_termination | `rag, calculator` | `rag, calculator` | ✅ PASS | none | 4.01s | 3 |
| p3b_prem_009 | premature_termination | `web_search, calculator` | `web_search, calculator` | ✅ PASS | none | 7.73s | 4 |
| p3b_prem_010 | premature_termination | `web_search, calculator` | `web_search, calculator` | ✅ PASS | none | 5.95s | 4 |
| p3b_dep_001 | multistep_dependency | `web_search, web_search, calculator` | `web_search, web_search` | ❌ FAIL | premature_stop | 8.68s | 4 |
| p3b_dep_002 | multistep_dependency | `web_search, web_search, calculator` | `web_search, calculator, web_search` | ❌ FAIL | wrong_order | 13.52s | 5 |
| p3b_dep_003 | multistep_dependency | `web_search, web_search, calculator` | `web_search, calculator` | ❌ FAIL | wrong_order | 5.67s | 4 |
| p3b_dep_004 | multistep_dependency | `web_search, web_search, calculator, calculator` | `web_search, calculator` | ❌ FAIL | wrong_order | 6.70s | 4 |
| p3b_dep_005 | multistep_dependency | `web_search, web_search, calculator` | `web_search, web_search, calculator` | ✅ PASS | none | 10.63s | 5 |
| p3b_dep_006 | multistep_dependency | `rag, web_search, calculator` | `rag, web_search, calculator, web_search` | ❌ FAIL | wrong_order | 9.19s | 5 |
| p3b_dep_007 | multistep_dependency | `rag, web_search, calculator` | `rag, calculator, web_search` | ❌ FAIL | wrong_order | 6.67s | 4 |
| p3b_dep_008 | multistep_dependency | `rag, web_search` | `rag, web_search` | ✅ PASS | none | 5.07s | 3 |
| p3b_dep_009 | multistep_dependency | `rag, web_search` | `rag, web_search` | ✅ PASS | none | 4.58s | 3 |
| p3b_dep_010 | multistep_dependency | `web_search, web_search, calculator` | `web_search, web_search, calculator` | ✅ PASS | none | 10.94s | 5 |

## 5. Architectural Improvements Implemented in Phase 3B

1. **Strict Tool Necessity Boundary**:
   - Explicit prompt requirements that forbid mental arithmetic, forcing `calculator` invocation.
   - Clear separation between queries answerable strictly from retrieved RAG context vs. queries requiring subsequent arithmetic or external lookup.
2. **Deterministic Completion Guard (Zero-LLM Overhead)**:
   - Intercepts premature `action: final` decisions if explicit calculation or search operations from the user query have not been completed.
   - Re-prompts the planner with specific guard feedback, eliminating premature stops after step 1.
3. **Repeated Tool Loop Protection**:
   - Detects consecutive identical `(tool_name, arguments)` dispatches without new information and halts safely (`execution_status='repeated_tool_call'`).
4. **Exact Latency & Call Instrumentation**:
   - Traces precise per-step LLM and tool execution durations.
