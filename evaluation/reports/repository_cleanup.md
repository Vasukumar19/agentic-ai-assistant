# Repository Cleanup Report (Pre-Phase 13)

**Date**: 2026-08-26 · **Scope**: Repository structure consolidation, redundant script removal, test suite verification, and artifact preservation.

---

## 1. Files Removed (31 Files)

### One-Off Scratch Scripts & Temporary Experiments
- `test.py`
- `test_edge_cases.py`
- `generate_docs.py`
- `generate_eval_dataset.py`
- `generate_phase3_dataset.py`
- `_repeat_gemma.py`

### Obsolete Runner Helpers (`evaluation/runners/`)
- `evaluation/runners/_errors.py`
- `evaluation/runners/_gen_phase4_report.py`
- `evaluation/runners/_old_react_agent.py.bak`
- `evaluation/runners/_reaggregate.py`
- `evaluation/runners/_recover_react.py`
- `evaluation/runners/_regen_report.py`
- `evaluation/runners/_retry_errors.py`
- `evaluation/runners/_summarize.py`
- `evaluation/runners/gemma_smoke.py`
- `evaluation/runners/gemma_failure_analysis.py`
- `evaluation/runners/qwen3_smoke.py`
- `evaluation/runners/qwen3_local_eval.py`
- `evaluation/runners/react_agent_recovered.py`
- `evaluation/runners/react_benchmark.py`
- `evaluation/runners/refresh_web_bands.py`

### Temporary Checkpoints & Intermediate Outputs (`evaluation/results/`)
- `evaluation/results/phase11_context_checkpoint.json`
- `evaluation/results/phase11_replanning_checkpoint.json`
- `evaluation/results/phase11_verifier_checkpoint.json`
- `evaluation/results/phase10_metadata_checkpoint.json`
- `evaluation/results/phase10_llm_checkpoint.json`
- `evaluation/results/phase9_gemma_budget10_checkpoint.json`
- `evaluation/results/phase4_final_log.txt`
- `evaluation/results/phase4_full_run2.json`
- `evaluation/results/phase4_mem_recheck2.json`
- `evaluation/results/phase4_mem_recheck3.json`

---

## 2. Files Moved
- None. (MCP server implementations `mcp_calendar_server.py`, `mcp_notes_server.py`, `mcp_reminders_server.py`, `mcp_filesystem_server.py`, `mcp_test_server.py` were intentionally retained at root to preserve stdio subprocess launch contracts across `config.py` and evaluation runners without breaking runtime behavior).

---

## 3. Tests Retained (22 Test Files)

| Test File | Subsystem Protected |
|---|---|
| `test_dynamic_discovery.py` | Phase 10 Dynamic Discovery |
| `test_evaluation.py` | Evaluation Metrics & Scoring |
| `test_execution_budget.py` | Execution Budget & Step Limits |
| `test_gemma_structured.py` | Model Output Schema Compatibility |
| `test_hybrid_planner.py` | Hybrid Planner Orchestration |
| `test_llm_call_counters.py` | Observability & Call Counting |
| `test_mcp_efficiency.py` | MCP Performance & Batch Efficiency |
| `test_mcp_foundation.py` | Core MCP Client & Registry |
| `test_mcp_multiserver.py` | Multi-Server Tool Routing & Execution |
| `test_mcp_naming.py` | Tool Name Resolution & Namespace Registry |
| `test_mcp_real_filesystem.py` | Real Filesystem MCP & Path Security |
| `test_memory_agent.py` | Persistent Memory Read/Write |
| `test_memory_nodes.py` | Memory Extraction & Merging |
| `test_phase4_metrics.py` | Groundedness & Quality Metrics |
| `test_planner_reliability.py` | Planner Calculation Guard & Loop Protection |
| `test_planning_strategies.py` | Planning Schema, DAG Validation & Replan State |
| `test_qwen3_structured.py` | Qwen3 Structured Output Parser |
| `test_qwen3_tool_calling.py` | Qwen3 Tool Binding & Execution |
| `test_reliability_phase5.py` | Observability, Tracing, Retry, Timeout & Circuit Breaker |
| `test_result_aware_replanning.py` | Result-Aware Replanning & Loop Detection |
| `test_result_aware_security.py` | Tool Output Prompt Injection Security |
| `test_rrf.py` | RRF Fusion Algorithm |

---

## 4. Tests Removed
- None (Zero production test coverage deleted).

---

## 5. Tests Merged
- None.

---

## 6. Generated Artifacts Removed
- Intermediate checkpoints (`*checkpoint.json`) and transient output logs (`phase4_final_log.txt`).

---

## 7. Production Files Untouched
- `config.py`, `graph.py`, `state.py`, `llm.py`, `ingest.py`, `reranker.py`
- All files in `nodes/` (`planner_node.py`, `router.py`, `context_builder.py`, `memory_extractor.py`, `memory_retriever.py`, `rag_retriever.py`, `tools.py`, `chat.py`, `bm25.py`, `embeddings.py`, `rrf.py`, `retrieval_planner.py`)
- All files in `mcp_layer/` (`adapter.py`, `client.py`, `discovery.py`, `errors.py`, `models.py`, `registry.py`)
- All files in `observability/` (`errors.py`, `ids.py`, `redaction.py`, `retry.py`, `storage.py`, `timeout.py`, `trace.py`)
- All files in `planning/` (`classifier.py`, `schema.py`, `validation.py`)

---

## 8. Benchmark Datasets Preserved
- `phase3_live.json`, `phase3b_dataset.json`, `phase4_ground_truth.json`, `phase5_observability_cases.json`, `phase6a_mcp_cases.json`, `phase6b_real_mcp.json`, `phase6c_multiserver.json`, `phase7_strategy_dataset.json`, `phase7b_adaptive_dataset.json`, `phase8_budget_dataset.json`, `phase9_gemma_60cases.json`, `phase10_discovery_dataset.json`, `phase11_multihop_diagnostic.json`, `phase11_visibility_horizon.json`, `phase12_diagnostic.json`.

---

## 9. Historical Reports Preserved
- All 22 phase reports in `evaluation/reports/` (`phase3_baseline.md` through `phase12_completion_context.md`, `phase11_result_aware_replanning.md`, `gemma3_12b_model_comparison.md`, `phase10_dynamic_tool_filtering.md`, `phase11_failure_forensics.md`).

---

## 10. Final Test Count
- **213 Tests PASSED** across 22 test files.

---

## 11. Final Repository Structure

```text
agentic-ai-assistant/
├── config.py
├── graph.py
├── state.py
├── llm.py
├── ingest.py
├── reranker.py
├── mcp_calendar_server.py
├── mcp_notes_server.py
├── mcp_reminders_server.py
├── mcp_filesystem_server.py
├── mcp_test_server.py
├── pytest.ini
├── requirements.txt
├── README.md
├── nodes/
├── mcp_layer/
├── planning/
├── observability/
├── evaluation/
│   ├── datasets/
│   ├── metrics/
│   ├── reports/
│   ├── results/
│   ├── runners/
│   ├── tests/
│   └── traces/
└── scripts/
```

---

## 12. Questionable Files Intentionally Retained
- `mcp_test_server.py`: Intentionally retained because unit tests (`test_mcp_foundation.py`, `test_mcp_efficiency.py`, `test_mcp_naming.py`) launch it directly via stdio to validate mock server interactions.
