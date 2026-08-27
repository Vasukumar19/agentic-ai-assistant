# Agentic AI Assistant — Architecture Specification (V1 Production Freeze)

## 1. System Overview

The **Agentic AI Assistant** is an agentic system designed to run on local edge hardware with small language models (e.g., `Qwen3:8b` via Ollama). It coordinates tools and services across the **Model Context Protocol (MCP)** using deterministic completion guards, result-aware replanning, compact workflow progress memory, and security protections.

---

## 2. High-Level Architecture Flow

```text
               ┌────────────────────────┐
               │       User Query       │
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │     Intent Router      │
               └───────────┬────────────┘
                           │
                           ▼
               ┌────────────────────────┐
               │    Context Builder     │
               └───────────┬────────────┘
                           │
                           ▼
           ┌─────────► ┌────────────────────────┐
           │           │   Hybrid Planner Node  │
           │           │       (Qwen3:8b)       │
           │           └───────────┬────────────┘
           │                       │
           │          Action: Tool │ Action: Final
           │                       ▼                       ▼
           │           ┌────────────────────────┐  ┌────────────────────────┐
           │           │  MCP / Tool Execution  │  │ Goal Fulfillment Guard │
           │           │  - Sandboxed Filesystem│  └───────────┬────────────┘
           │           │  - Stdio Local Servers │              │
           │           │  - Human Confirmation  │     ┌────────┴────────┐
           │           └───────────┬────────────┘     │                 │
           │                       │              FULFILLED         INCOMPLETE
           │                       ▼                  │                 │
           │           ┌────────────────────────┐     ▼                 │
           │           │  Result-Aware Progress │   FINAL ANSWER        │
           │           │   Workflow Context     │                       │
           │           └───────────┬────────────┘                       │
           └───────────────────────┴────────────────────────────────────┘
```

---

## 3. Core Subsystems

### A. State Management (`state.py`)
All execution state is centralized in `AgentState`:
- `question`, `route`, `answer`
- `completed_steps`, `current_step`, `tool_results`, `execution_status`
- `required_operations`, `completed_operations`, `remaining_operations`
- `trace_events`, `latency_breakdown`, `llm_usage`
- `argument_repair_attempts`

### B. Hybrid Planner (`nodes/planner_node.py`)
- Direct JSON structured decision generation using Pydantic schemas (`PlannerDecision`).
- Supports single-step decision making with compact workflow progress tracking (`PLANNER_COMPLETION_CONTEXT=on`).

### C. Result-Aware Replanning & Completion Memory
- Tools outputs are bounded to `<= 500` characters to prevent prompt bloat on local context windows.
- Tool outputs are treated strictly as **DATA**, not instructions (preventing prompt injection).
- A compact progress summary block keeps the small 8B model aware of completed operations without confusing it with noisy intermediate output.

### D. Deterministic Goal Fulfillment Guard (`planning/goal_guard.py`)
- Generic capability extraction parses required operation verbs (`read`, `calculate`, `create`, `list`, `update`, `delete`) with **zero hardcoded service keywords**.
- When the planner proposes `action == "final"`, the guard evaluates `goal_fulfillment_check()`.
- If required operations remain unexecuted, `final` is rejected and the planner is re-prompted with the remaining operations.

### E. Bounded MCP Argument Auto-Healing
- Structured validation errors (missing parameters, incorrect types) allow `MAX_ARGUMENT_REPAIR_ATTEMPTS = 1`.
- If the repair fails, it terminates honestly without entering infinite loops.

### F. Model Context Protocol (MCP) Architecture (`mcp_layer/`)
- Unified `ToolRegistry` managing native tools (`calculator`, `web_search`) and MCP tools (`calendar.*`, `notes.*`, `reminders.*`, `filesystem.*`).
- Isolated stdio subprocesses for local services with hardened exception handling preventing `anyio` `TaskGroup` crashes.

---

## 4. Safety & Security Safeguards

1. **Human Confirmation Hook**: Destructive actions (`delete_event`, `delete_note`, `delete_reminder`) strictly require human confirmation before execution.
2. **Filesystem Sandbox**: All file operations are restricted to `mcp_sandbox/`; directory traversal (`../`) is blocked and returns permission errors.
3. **Loop Protection**: Alternating and consecutive loop detection halts repetitive invocations on static data.
4. **Execution Budget**: Strict hard limit of `MAX_EXECUTION_STEPS = 10` preventing runaway loops.
5. **Redaction & Observability**: Secrets, tokens, and raw prompt chains are excluded from structured trace events.
