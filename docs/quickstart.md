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
| **Path** | `intent_router` → `retrieval_planner` → `memory_retriever` → `context_builder` → `agent` → `save_history` |
| **Planner** | `{profile: true, semantic: false, rag: false}` via `"my name"` heuristic |
| **Expected output** | Answer using profile context, e.g. states stored name |

If `memory.json` is empty or missing, agent receives no profile context and may not know the name.

---

### Calculator

**Input:**

```
What is 157 * 23?
```

| | |
|---|---|
| **Expected route** | `research_query` |
| **Path** | research path + possible tool loop |
| **Planner** | Likely all false (no profile/semantic/rag hints) |
| **Expected output** | Agent calls `calculator` tool, then returns numeric result |

**Tool loop:**

```
Question
   ↓
Agent (requests calculator tool)
   ↓
ToolNode (runs calculator)
   ↓
Agent (returns final answer)
   ↓
save_history
```

---

### Web Search

**Input:**

```
What is the current price of gold?
```

| | |
|---|---|
| **Expected route** | `research_query` |
| **Planner** | Likely all false |
| **Expected output** | Agent calls `web_search` via DuckDuckGo, summarizes results |

Requires network access. DuckDuckGo rate limits or blocks may cause tool errors.

---

### Tool Loop (Multi-Step)

**Input:**

```
Calculate sqrt(144) and then multiply the result by 5
```

| | |
|---|---|
| **Expected route** | `research_query` |
| **Max iterations** | 5 tool rounds (`MAX_TOOL_ITERATIONS`) |

```
Question
   ↓
Agent → may call calculator
   ↓
ToolNode → ToolMessage in state.messages
   ↓
Agent → final answer (or another tool call, up to limit)
   ↓
save_history
```

If max iterations is reached with tool calls still pending, graph routes to `save_history` with fallback answer if `answer` is still empty.

---

### RAG / Company Documents

**Prerequisite:** `faiss_index/` exists at project root.

**Input:**

```
What is the company policy on remote work?
```

| | |
|---|---|
| **Expected route** | `research_query` |
| **Planner** | `{rag: true}` via policy heuristic |
| **Path** | includes `rag_retriever` → `context_builder` → `agent` |
| **Expected output** | Answer grounded in retrieved document chunks |

Without `faiss_index/`, RAG retriever returns empty context and the agent answers without document grounding.

---

## Troubleshooting

### Missing API key

**Symptom:**

```
EnvironmentError: GROQ_API_KEY not found. Please add it to your .env file.
```

**Fix:**

1. Create `.env` in the project root.
2. Add `GROQ_API_KEY=...`
3. Restart the application.

---

### Missing FAISS / dependency errors

**Symptom:**

```
ModuleNotFoundError: No module named 'faiss'
```

**Fix:**

```bash
pip install faiss-cpu
```

Already pinned in `requirements.txt` as `faiss-cpu==1.8.0`.

---



### Missing FAISS index (`faiss_index/`)

**Symptom (console):**

```
[RAG Retriever] No documents found (faiss_index not built)
```

**Behavior:** Graph continues. RAG context is empty. Agent answers without document retrieval.

**Fix:** Build or copy a FAISS index into `faiss_index/` at the project root. The repository does not include an index builder script.

---

### Missing profile memory

**Symptom:** `"What's my name?"` returns a generic or unknown answer.

**Cause:** `memory/memory.json` does not exist or has no `name` field.

**Fix:** Store memory first:

```
My name is Alice.
```

Then ask retrieval questions.

---

### Missing semantic memory index

**Symptom:**

```
[Memory Retriever] Error loading semantic memory FAISS index
```

**Behavior:** Semantic context stays empty; graph continues.

**Fix:** Save semantic memories via the memory update path, which creates `memory/semantic_memory/`.

---

### Empty or corrupt chat history

**Symptom:** Prior turns not loaded.

**Behavior:** `load_chat_history()` returns `[]` on missing file or parse error.

**Fix:** Delete or repair `memory/chat_history.json`. File must be a JSON array of `{role, content}` objects.

---

### Groq / network errors

**Symptom:**

```
[Error] ...
Answer: I encountered an error processing your request. Please try again.
```

**Fix:** Check API key validity, Groq service status, and network connectivity.

**For Rate Limit Errors (429):**
If you encounter a `RateLimitError` (especially for Tokens Per Day on the free tier), open `config.py` and change `MODEL_NAME` to a smaller model, such as `llama-3.1-8b-instant` or `mixtral-8x7b-32768`.

---

### DuckDuckGo search failures

**Symptom:** Tool returns error string; agent may still respond with partial info.

**Fix:** Retry later, check network, verify `duckduckgo-search` is installed.

---

### Embedding model download slow or fails

**Symptom:** Long pause on first memory/RAG operation; or HuggingFace download error.

**Fix:** Ensure internet access and disk space. Model: `sentence-transformers/all-MiniLM-L6-v2`.

---

### Tests fail to import `langchain_core`

**Symptom:**

```
ModuleNotFoundError: No module named 'langchain_core'
```

**Fix:** Activate the virtual environment and run `pip install -r requirements.txt`.

---

## Configuration Reference

All tunables in [`config.py`](../config.py):

| Setting | Default | Purpose |
|---------|---------|---------|
| `MODEL_NAME` | `llama-3.3-70b-versatile` | Groq model |
| `TEMPERATURE` | `0.3` | LLM temperature |
| `MAX_TOOL_ITERATIONS` | `5` | Tool loop cap |

---

## Further Reading

| Document | Contents |
|----------|----------|
| [graphvisual.md](./graphvisual.md) | Full graph diagram, node I/O, state ownership, performance |
| [implementation.md](./implementation.md) | File-by-file guide, execution flows, design decisions, extension patterns |
