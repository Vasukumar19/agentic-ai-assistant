# Research & Architecture Evolution History (Phases 6–13.1)

This document records the empirical research findings, controlled benchmark experiments, and architectural decisions that led to the V1 production architecture.

---

## Phase 6: MCP Foundation
- **Question**: Can we unify native tools and external services using the official Model Context Protocol without breaking LangGraph state?
- **Experiment**: Implemented `mcp_layer/` (`MCPClient`, `ToolRegistry`, `adapter.py`) with stdio JSON-RPC transport.
- **Decision**: Adopted MCP as the standard abstraction layer for all tool interactions.

---

## Phase 6B: Sandboxed Filesystem MCP
- **Question**: Can we provide real filesystem access to the agent without risking local machine security?
- **Experiment**: Implemented `mcp_filesystem_server.py` restricted to `mcp_sandbox/` with strict path traversal checking.
- **Decision**: Retained sandboxed filesystem as a core MCP tool.

---

## Phase 6C: Multi-Server Coordination Benchmark
- **Question**: How well does a local 8B model coordinate multiple independent MCP servers (Calendar, Notes, Reminders)?
- **Experiment**: Constructed a frozen 60-case multi-server benchmark covering 1-service, 2-service, and 3-service workflows.
- **Findings**: Baseline model achieved only 50.0% completion with severe premature termination on 3-service tasks (20.0%).

---

## Phase 7: Planning Strategy Investigation
- **Question**: Does multi-step pre-planning (RePlan, DAGs) improve tool coordination over single-step decisions?
- **Experiment**: Evaluated single-step, full-plan, and hybrid adaptive planners.
- **Decision**: Retained **Hybrid Planning** (`PLANNING_STRATEGY=hybrid`), as full DAG generation caused rigid failure cascades when tool outputs deviated from initial assumptions.

---

## Phase 8: Execution Budget & Loop Detection
- **Question**: How do we prevent infinite loops on small local models without halting legitimate multi-step workflows?
- **Experiment**: Implemented signature-and-result alternating loop detection and calibrated execution budget (`MAX_EXECUTION_STEPS=10`).
- **Decision**: Adopted state-aware loop detection.

---

## Phase 9: Gemma 3 12B vs Qwen 3 8B Comparison
- **Question**: Does scaling from an 8B to a 12B model (`gemma3:12b`) fix multi-server tool orchestration?
- **Experiment**: Benchmarked Gemma 3 12B against Qwen 3 8B on identical 60-case frozen dataset.
- **Findings**: Gemma 3 12B reduced premature stops but suffered a 13.7pp drop in multi-server tool selection accuracy and tripled latency (19.1s → 56.3s).
- **Decision**: Scale upgrade rejected; **`Qwen3:8b` retained as production baseline**.

---

## Phase 10: Dynamic MCP Tool Discovery Filtering
- **Question**: Does pre-filtering available tools before the planner reduce cognitive load and improve completion?
- **Experiment**: Evaluated Metadata Similarity (Variant A) and LLM-Assisted Discovery (Variant B).
- **Findings**: Pre-planner filtering degraded overall completion (60.3% → 51.7%) due to visibility-horizon errors where subsequent required tools were filtered out before step 1.
- **Decision**: Pre-planner filtering rejected (`DISCOVERY_STRATEGY=none`); all registered tools remain available to the planner.

---

## Phase 11: Result-Aware Replanning
- **Question**: Does giving the planner compact summaries of prior tool outputs improve dependency tracking?
- **Experiment**: Injected bounded tool results (<= 500 chars) into user prompt (`RESULT_AWARE_REPLANNING=on`).
- **Findings**: Improved dependency accuracy from 79.3% → 86.2% (+6.9pp) and 1-service completion to 90.0% (+20.0pp).
- **Decision**: Retained in production.

---

## Phase 12: Planner Completion Context
- **Question**: Does an explicit workflow progress block reduce latency and improve 3-service completion?
- **Experiment**: Injected `WORKFLOW PROGRESS` memory block (`PLANNER_COMPLETION_CONTEXT=on`).
- **Findings**: Improved 3-service completion from 20.0% → 30.0% (+10.0pp) and reduced mean latency by 3.71s (-17.2%).
- **Decision**: Retained in production.

---

## Phase 13: Goal Fulfillment & MCP Reliability
- **Question**: How can we eliminate the remaining 70% failure rate in 3-service orchestration and prevent premature stops?
- **Experiment**: Implemented Deterministic Goal Fulfillment Guard (`planning/goal_guard.py`), Bounded MCP Argument Repair, and MCP Server Exception Hardening.
- **Findings**: Overall completion jumped from **61.4% → 90.0%** (+28.6pp), 3-service completion jumped from **30.0% → 100.0%** (+70.0pp), and premature termination dropped from **28.1% → 0.0%**.
- **Decision**: Retained in production.

---

## Phase 13.1: Reproducibility & Production Freeze Gate
- **Question**: Is Phase 13's breakthrough reproducible across multiple independent runs?
- **Experiment**: Executed 3 independent 60-case benchmark passes (Original, Repeat A, Repeat B = 180 total executions).
- **Findings**: Sustained **87.8% mean completion**, **96.3% 3-service completion**, **100% 1-service completion**, and **0.0% premature termination** across all 180 runs with zero subprocess crashes.
- **Decision**: **Frozen as V1 Production Baseline**.
