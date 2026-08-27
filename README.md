# Agentic AI Assistant (V1 Production Freeze)

An enterprise-grade, local-first **Agentic AI Assistant** powered by small open-weights language models (`Qwen3:8b` via Ollama) and the **Model Context Protocol (MCP)**. 

Built with **deterministic goal fulfillment guards**, **result-aware replanning**, **compact workflow memory**, and **hardened subprocess isolation**, this system achieves **96.3% multi-service orchestration reliability** and **0% premature termination** on local edge hardware.

---

## Architecture Overview

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

## Core Capabilities & Features

- **100% Local & Offline**: Powered by Ollama (`qwen3:8b`) with zero cloud dependencies or API keys required.
- **Model Context Protocol (MCP)**: Native integration with standardized MCP servers (`calendar`, `notes`, `reminders`, `filesystem`).
- **Deterministic Goal Fulfillment Guard**: Generic verb capability extraction preventing premature task finalization.
- **Result-Aware Context & Bounded Memory**: Compact progress summaries preventing small-model cognitive overload.
- **Auto-Healing Argument Repair**: 1-step bounded schema repair on parameter validation errors.
- **Robust Security & Policy Engine**:
  - **Human-in-the-Loop Confirmation**: Destructive operations (`delete`) require explicit human authorization.
  - **Filesystem Sandboxing**: All file I/O is restricted to `mcp_sandbox/` with path-traversal prevention.
  - **Loop Detection & Execution Budgets**: Signature-and-result alternating loop detection with a 10-step hard execution cap.
  - **Subprocess Exception Hardening**: Zero `TaskGroup` leaks; all errors are cleanly converted to structured JSON.

---

## Verified Benchmark Results

Measured across 3 independent controlled evaluations (180 total query executions on frozen 60-case benchmark):

| Category | Baseline (Phase 12) | V1 Production (Phase 13.1) | Net Gain |
|---|---:|---:|---|
| **Overall Completion** | 61.4% | **87.8%** | **+26.4 pp** |
| **1-Service Tasks** | 90.0% | **100.0%** (10/10) | **+10.0 pp** |
| **2-Service Tasks** | 55.6% | **78.1%** (25/32) | **+22.5 pp** |
| **3-Service Tasks** | 30.0% | **96.3%** (9/9) | **+66.3 pp** |
| **Premature Termination** | 28.1% | **0.0%** | **-28.1 pp** (0 stops) |
| **MCP Subprocess Crashes** | ~5.0% | **0.0%** | **0 crashes** |
| **Mean Latency** | 17.90s | **17.34s** | **-0.56s** |
| **P95 Latency** | 36.20s | **35.01s** | **-1.19s** |

---

## Quickstart & Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.12)
- [Ollama](https://ollama.ai) installed and running locally
- GPU with >= 6GB VRAM (or CPU mode)

### 2. Pull the Local Model
```bash
ollama pull qwen3:8b
```

### 3. Setup Virtual Environment
```bash
git clone https://github.com/Vasukumar19/agentic-ai-assistant.git
cd agentic-ai-assistant
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
```

---

## Running the Assistant

### Interactive Mode
```bash
python main.py
```

### Single Query Mode
```bash
python main.py "Read note note_001, calculate 15% of the total inside, and save a reminder."
```

---

## Running Verification & Tests

### 1. One-Command Production Smoke Test (< 15 seconds)
```bash
python scripts/smoke_test.py
```

### 2. Full Unit & Integration Test Regression Suite
```bash
python -m pytest evaluation/tests/ -v
```

---

## Project Structure

```text
agentic-ai-assistant/
├── main.py                       # One-command production startup CLI
├── config.py                     # Centralized environment configuration
├── state.py                      # Unified AgentState definition
├── graph.py                      # LangGraph workflow compilation
│
├── nodes/                        # Core graph nodes
│   ├── planner_node.py           # Hybrid planner with goal guard & repair
│   ├── tools.py                  # Tool execution & confirmation gating
│   ├── router.py                 # Intent routing
│   └── context_builder.py        # Context aggregation
│
├── planning/                     # Deterministic verification
│   └── goal_guard.py             # Capability-level goal check
│
├── mcp_layer/                    # Model Context Protocol abstraction
│   ├── client.py                 # Stdio MCP client
│   ├── registry.py               # Unified tool registry & policies
│   ├── adapter.py                # LangChain tool adapter
│   └── models.py                 # Normalized schemas
│
├── mcp_calendar_server.py        # Local Calendar MCP server (stdio)
├── mcp_notes_server.py           # Local Notes MCP server (stdio)
├── mcp_reminders_server.py       # Local Reminders MCP server (stdio)
├── mcp_filesystem_server.py      # Local Filesystem MCP server (sandboxed)
│
├── observability/                # Tracing, redaction, and metrics
├── scripts/                      # Operational utilities (smoke_test.py)
├── docs/                         # Architecture, MCP guide, and research history
└── evaluation/                   # Frozen benchmarks, runners, and reports
```

---

## License & Contributing
This repository is maintained as a reproducible agentic AI research and production template. MIT Licensed.
