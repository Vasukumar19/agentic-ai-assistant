# Agentic AI Assistant — Quickstart Guide

Onboarding guide for running, configuring, and testing the Agentic AI Assistant.

---

## Prerequisites

- Python 3.10+ (tested on Python 3.12)
- [Ollama](https://ollama.ai) installed and running locally
- (Optional) API keys for Anthropic, OpenAI, Google, or Groq if testing cloud providers

---

## Installation

### 1. Clone the project
```bash
git clone https://github.com/Vasukumar19/agentic-ai-assistant.git
cd agentic-ai-assistant
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Pull the local LLM model
```bash
ollama pull qwen3:8b
```

### 5. Setup Configuration
Copy the example environment file:
```bash
cp .env.example .env
```

### 6. Ingest Knowledge Base (for RAG)
```bash
python ingest.py
```

---

## Running Locally

### Interactive CLI Mode
```bash
python main.py
```

Type queries at the prompt. Special commands:
- `help`: View guidance and sample queries
- `clear`: Clear screen
- `q` or `exit`: Exit the assistant

### Single Query Mode
```bash
python main.py "What is our company remote work policy?"
```

---

## Testing & Verification

### 1. Production Smoke Test
```bash
python scripts/smoke_test.py
```

### 2. Full Automated PyTest Suite
```bash
python -m pytest tests/ -v
```

---

## Example Interactions

Below are realistic examples with **expected route** and **expected behavior** based on current pre-routing and heuristics. Exact LLM wording will vary.

### Chat

**Input:**

```
hello
```

| | |
|---|---|
| **Expected route** | `chat` (pre-routed greeting, no router LLM) |
| **Path** | `intent_router` → `chat` → `save_history` |
| **Expected output** | Conversational greeting from LLM |
| **LLM calls** | 1 |

**Edge case:** `"hello, what is my name?"` matches greeting pre-route first → `chat`, not research. This is current behavior.

---

### Memory Update

**Input:**

```
My name is Kumar and I am learning LangGraph.
```

| | |
|---|---|
| **Expected route** | `memory_update` (declarative statement, router LLM) |
| **Path** | `intent_router` → `memory_extractor` → `memory_saver` → `memory_response` → `save_history` |
| **Expected output** | Confirmation like `Got it! I'll remember that your name is Kumar, ...` |
| **Side effects** | Updates `memory/memory.json`; may add semantic FAISS entry |

**Edge case:** `"What is my name?"` is pre-routed to `research_query`, not memory update.

---

### Memory Retrieval

**Prerequisite:** Profile saved (e.g., name in `memory/memory.json`).

**Input:**
```
What's my name?
```

| | |
|---|---|
| **Expected route** | `research_query` (question pre-route) |
| **Path** | `intent_router` → `retrieval_planner` → `memory_retriever` → `context_builder` → `planner` → `save_history` |
| **Planner** | `{profile: true, semantic: false, rag: false}` via `"my name"` heuristic |
| **Expected output** | Answer using profile context, stating stored user name |

---

### Calculator

**Input:**
```
What is 157 * 23?
```

| | |
|---|---|
| **Expected route** | `research_query` |
| **Path** | research path + tool loop |
| **Expected output** | Planner calls `calculator` tool, then returns numeric result (3611) |

---

### Multi-Server Compound Action Workflow

**Input:**
```
Read the note titled 'Quarterly Planning', calculate a 15% increase on the budget inside, and schedule a calendar event for tomorrow at 2 PM.
```

| | |
|---|---|
| **Expected route** | `research_query` |
| **Execution Steps** | 1. `notes.list` / `notes.get` → 2. `calculator` → 3. `calendar.create_event` → 4. `planner` final answer |
| **Safeguards** | Goal fulfillment guard ensures all 3 operations finish before terminating |

---

### Hybrid RAG / Enterprise Knowledge Query

**Prerequisite:** Knowledge base ingested via `python ingest.py`.

**Input:**
```
What is the company policy on remote work?
```

| | |
|---|---|
| **Expected route** | `research_query` |
| **Planner** | `{rag: true}` via policy heuristic |
| **Path** | `rag_retriever` (FAISS + BM25 + RRF + Reranker) → `context_builder` → `planner` |
| **Expected output** | Answer grounded in retrieved document chunks from `documents/` |

---

## Troubleshooting

### Ollama Connectivity Error

**Symptom:**
```
[ERROR] Ollama is not accessible on http://localhost:11434
```

**Fix:**
1. Make sure Ollama desktop is running.
2. In terminal run: `ollama run qwen3:8b`.
3. Verify connectivity at `http://localhost:11434`.

---

### Missing FAISS Vector Index (`faiss_index/`)

**Symptom:**
```
[RAG Retriever] FAISS index directory not found at faiss_index (index not built)
```

**Fix:** Run the ingestion pipeline to build both FAISS and BM25 indices:
```bash
python ingest.py
```

---

### Missing Profile Memory

**Symptom:** `"What's my name?"` returns a generic answer.

**Fix:** Store memory first:
```
My name is Alice.
```
Then ask retrieval questions.

---

### Resetting Sandbox & Server Data

To reset calendar, notes, reminders, or database state:
```bash
# Clear JSON stores
rm mcp_data/*.json
```

---

## Configuration Reference

All tunables in [`config.py`](../config.py):

| Setting | Default | Purpose |
|---------|---------|---------|
| `LLM_PROVIDER` | `"ollama"` | LLM provider (`ollama`, `anthropic`, `openai`, `google`, `groq`) |
| `LLM_MODEL` | `"qwen3:8b"` | Model name |
| `OLLAMA_BASE_URL` | `"http://localhost:11434"` | Ollama endpoint |
| `MAX_EXECUTION_STEPS` | `10` | Hard cap on multi-step tool loops |
| `RETRIEVAL_MODE` | `"hybrid"` | RAG search strategy (`hybrid`, `faiss`, `rrf`, `reranker`) |
| `RRF_K` | `60` | Reciprocal Rank Fusion constant |
| `TRACE_DIR` | `PROJECT_ROOT / "traces"` | Execution trace directory |

---

## Further Reading

| Document | Contents |
|----------|----------|
| [architecture.md](./architecture.md) | Full system topology, safety policies, and components |
| [graphvisual.md](./graphvisual.md) | LangGraph visual flow, node I/O, and state ownership |
| [implementation.md](./implementation.md) | Complete file-by-file implementation guide |
| [mcp.md](./mcp.md) | Model Context Protocol integration and server developer guide |
| [real_applications.md](./real_applications.md) | GitHub, SQLite, and Web Fetch server guides |

