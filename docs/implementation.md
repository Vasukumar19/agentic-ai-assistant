# LangGraph Agent — Implementation Guide

This guide explains how the LangGraph Agentic AI project is implemented today. All descriptions are derived from the current source code.

---

## 1. Project Overview

### What this project is

A Python CLI agent that routes each user message through a **LangGraph `StateGraph`**. Depending on intent, it either:

- replies directly (`chat`),
- extracts and stores personal memory (`memory_update`), or
- plans retrieval, gathers context, reasons, and optionally calls tools (`research_query`).

### Core concepts

| Concept | Implementation |
|---------|----------------|
| **LangGraph** | Workflow orchestration library (`langgraph==0.1.17`) |
| **StateGraph** | Built in [`graph.py`](../graph.py) with typed state [`AgentState`](../state.py) |
| **Nodes** | Plain Python callables under [`nodes/`](../nodes/) |
| **AgentState** | Shared dict-like state passed between nodes |
| **Conditional edges** | Python functions return next node name(s) |
| **Fan-out** | `Send(...)` in `fan_out_retrievers()` for parallel retrieval |
| **Tool loop** | `agent` ↔ `tools` until no tool calls or max iterations |

### High-level architecture (post-refactor)

Three responsibilities were split into dedicated nodes:

```
Router          → classifies route only
Memory Extractor → extracts memory only
Retrieval Planner → builds retrieval_plan only
```

The agent node handles reasoning and optional tool use. Retrieval and memory persistence are graph nodes, not LLM tools.

---

## 2. File Reference

### [`agent_langgraph.py`](../agent_langgraph.py)

| | |
|---|---|
| **Purpose** | Application entry point and interactive CLI |
| **Responsibilities** | Load env, validate API key, compile graph, run queries, load/save conversation history |
| **Key functions** | `load_chat_history()`, `ask()`, `main()` |
| **Inputs** | User string via CLI or argv |
| **Outputs** | Printed answer; persisted history via graph's `save_history` node |
| **Dependencies** | `graph`, `state`, `config`, `langchain_core.messages` |

**Startup sequence:**

1. `load_dotenv()`
2. Verify `GROQ_API_KEY`
3. `create_runnable_graph()` once at import time
4. Interactive loop or single-shot CLI argument

**Initial state** created in `ask()`:

```python
{
    "question": question,
    "route": "",
    "retrieval_plan": {"profile": False, "semantic": False, "rag": False},
    "profile_context": "",
    "semantic_context": "",
    "rag_context": "",
    "extracted_profile": {},
    "extracted_semantic": [],
    "answer": "",
    "_combined_context": "",
    "messages": load_chat_history(),
}
```

Safe defaults ensure the chat path never requires planner or extractor fields.

---

### [`graph.py`](../graph.py)

| | |
|---|---|
| **Purpose** | Construct and compile the LangGraph workflow |
| **Responsibilities** | Register nodes/edges, routing helpers, save history |
| **Key functions** | `build_graph()`, `create_runnable_graph()`, `route_from_router()`, `fan_out_retrievers()`, `should_continue()`, `save_history_node()` |
| **Inputs** | `AgentState` dict per invocation |
| **Outputs** | Compiled runnable graph; terminal state after invoke |
| **Dependencies** | `langgraph`, `state`, `config`, all node functions |

**Graph node names (LangGraph registry):**

| Registered name | Function |
|-----------------|----------|
| `intent_router` | `intent_router` |
| `chat` | `chat_node` |
| `memory_extractor` | `memory_extractor_node` |
| `memory_saver` | `memory_saver_node` |
| `memory_response` | `memory_response_node` |
| `retrieval_planner` | `retrieval_planner_node` |
| `memory_retriever` | `memory_retriever_node` |
| `rag_retriever` | `rag_retriever_node` |
| `context_builder` | `context_builder_node` |
| `agent` | `agent_node` |
| `tools` | `tool_node` |
| `save_history` | `save_history_node` |

---

### [`state.py`](../state.py)

| | |
|---|---|
| **Purpose** | Define the graph state schema |
| **Responsibilities** | TypedDict + message reducer |
| **Key type** | `AgentState` |
| **Dependencies** | `typing`, `langchain_core.messages`, `langgraph.graph.message.add_messages` |

**Fields:**

| Field | Type | Reducer |
|-------|------|---------|
| `question` | `str` | replace |
| `route` | `str` | replace |
| `retrieval_plan` | `Optional[dict]` | replace |
| `profile_context` | `str` | replace |
| `semantic_context` | `str` | replace |
| `rag_context` | `str` | replace |
| `extracted_profile` | `dict` | replace |
| `extracted_semantic` | `list` | replace |
| `answer` | `str` | replace |
| `_combined_context` | `str` | replace |
| `messages` | `Annotated[list, add_messages]` | append/merge |

Only `messages` uses a reducer. All other fields are overwritten by the node that returns them.

---

### [`config.py`](../config.py)

| | |
|---|---|
| **Purpose** | Centralized constants and filesystem paths |
| **Responsibilities** | Single source of truth for paths and model settings |
| **Dependencies** | `pathlib.Path` |

| Constant | Value / Path |
|----------|--------------|
| `PROJECT_ROOT` | Directory containing `config.py` |
| `MEMORY_DIR` | `PROJECT_ROOT / "memory"` |
| `SEMANTIC_MEMORY_DIR` | `MEMORY_DIR / "semantic_memory"` |
| `CHAT_HISTORY_PATH` | `MEMORY_DIR / "chat_history.json"` |
| `MEMORY_FILE` | `MEMORY_DIR / "memory.json"` |
| `FAISS_INDEX_DIR` | `PROJECT_ROOT / "faiss_index"` |
| `MODEL_NAME` | `"llama-3.3-70b-versatile"` |
| `TEMPERATURE` | `0.3` |
| `MAX_TOOL_ITERATIONS` | `5` |

---

### [`llm.py`](../llm.py)

| | |
|---|---|
| **Purpose** | Shared LLM singleton |
| **Responsibilities** | Load `.env`, read `GROQ_API_KEY`, create exactly one `ChatGroq` |
| **Exports** | `llm`, `GROQ_API_KEY` |
| **Dependencies** | `dotenv`, `langchain_groq`, `config` |

This is the **only** file that instantiates `ChatGroq(...)`.

Consumers: `router`, `chat`, `memory_extractor`, `retrieval_planner`, `agent`.

---

### [`nodes/router.py`](../nodes/router.py)

| | |
|---|---|
| **Purpose** | Intent classification |
| **Function** | `intent_router(state)` |
| **Inputs** | `question` |
| **Outputs** | `route` |
| **Dependencies** | `llm` |

**Does not:** extract memory, build retrieval plans, initialize unrelated state fields.

**Classification order:**

1. Python greeting detection → `chat`
2. Python question detection → `research_query`
3. LLM JSON classification → one of three routes
4. LLM failure → `research_query`

---

### [`nodes/chat.py`](../nodes/chat.py)

| | |
|---|---|
| **Purpose** | Small-talk responses |
| **Function** | `chat_node(state)` |
| **Inputs** | `question` |
| **Outputs** | `answer` |
| **Dependencies** | `llm` |

Passes a conversational system prompt along with the full chat history and current question to the LLM.

---

### [`nodes/memory_extractor.py`](../nodes/memory_extractor.py)

Three node functions in one file:

#### `memory_extractor_node`

| | |
|---|---|
| **Inputs** | `question` |
| **Outputs** | `extracted_profile`, `extracted_semantic` |
| **LLM** | Yes — JSON extraction prompt |

#### `memory_saver_node`

| | |
|---|---|
| **Inputs** | `extracted_profile`, `extracted_semantic` |
| **Outputs** | `{}` |
| **Side effects** | Writes `MEMORY_FILE`, updates `SEMANTIC_MEMORY_DIR` FAISS index |

#### `memory_response_node`

| | |
|---|---|
| **Inputs** | `extracted_profile`, `extracted_semantic` |
| **Outputs** | `answer` |
| **LLM** | No — template string |

---

### [`nodes/retrieval_planner.py`](../nodes/retrieval_planner.py)

| | |
|---|---|
| **Purpose** | Build retrieval plan for research queries |
| **Function** | `retrieval_planner_node(state)` |
| **Inputs** | `question` |
| **Outputs** | `retrieval_plan` dict |
| **Dependencies** | `llm` |

Runs only when `route == "research_query"`.

Heuristics first, LLM second, all-false fallback on parse error.

> File name is `retrieval_planner.py`, not `planner.py`.

---

### [`nodes/memory_retriever.py`](../nodes/memory_retriever.py)

| | |
|---|---|
| **Purpose** | Read profile JSON and search semantic FAISS |
| **Function** | `memory_retriever_node(state)` |
| **Inputs** | `question`, `retrieval_plan` |
| **Outputs** | `profile_context`, `semantic_context` |
| **Dependencies** | `config`, `embeddings`, `FAISS` |

Profile formatting includes labeled sections (`=== PROFILE INFORMATION ===`).

Semantic search uses `similarity_search(question, k=3)`.

---

### [`nodes/rag_retriever.py`](../nodes/rag_retriever.py)

| | |
|---|---|
| **Purpose** | Search company document FAISS index |
| **Function** | `rag_retriever_node(state)` |
| **Inputs** | `question`, `retrieval_plan` |
| **Outputs** | `rag_context` |
| **Dependencies** | `config`, `embeddings`, `FAISS` |

Expects a pre-built index at `FAISS_INDEX_DIR`. There is no index-building script in the current repository.

---

### [`nodes/context_builder.py`](../nodes/context_builder.py)

| | |
|---|---|
| **Purpose** | Merge retrieval strings |
| **Function** | `context_builder_node(state)` |
| **Inputs** | `profile_context`, `semantic_context`, `rag_context` |
| **Outputs** | `_combined_context` |

Pure string assembly — no I/O, no LLM.

---

### [`nodes/agent.py`](../nodes/agent.py)

| | |
|---|---|
| **Purpose** | Research-path reasoning and tool binding |
| **Function** | `agent_node(state)` |
| **Inputs** | `question`, `_combined_context`, `messages` |
| **Outputs** | `messages`; `answer` when finished |
| **Dependencies** | `llm`, `tools` |

Builds a `SystemMessage` with `AGENT_SYSTEM_PROMPT` and `_combined_context`, then prepends it to the conversation history (`state["messages"]`), ensures the current `question` is appended, and finally calls `llm.bind_tools(tools).invoke(llm_input)`.

---

### [`nodes/tools.py`](../nodes/tools.py)

| | |
|---|---|
| **Purpose** | Define and execute agent tools |
| **Exports** | `web_search_tool`, `calculator`, `tools`, `tool_node`, `run_tool` |
| **Dependencies** | `DuckDuckGoSearchRun`, `asteval`, `langgraph.prebuilt.ToolNode` |

| Tool | Backend |
|------|---------|
| `web_search` | DuckDuckGo via `langchain_community` |
| `calculator` | `asteval.Interpreter` |

Memory and RAG are intentionally **not** tools.

---

### [`nodes/embeddings.py`](../nodes/embeddings.py)

| | |
|---|---|
| **Purpose** | Shared embedding model singleton |
| **Exports** | `embeddings` |
| **Model** | `sentence-transformers/all-MiniLM-L6-v2` on CPU |

Used by semantic memory save/search and RAG search.

---

### [`nodes/__init__.py`](../nodes/__init__.py)

Re-exports all node functions for `graph.py` imports.

---

## 3. Detailed Execution Flows

### Chat Path

**Example:** `"hello"`

| Step | Node | State changes |
|------|------|---------------|
| 1 | `intent_router` | `route = "chat"` (pre-routed, no LLM) |
| 2 | `chat` | `answer = <LLM response>` |
| 3 | `save_history` | Appends user + assistant entries to `CHAT_HISTORY_PATH` |

**LLM calls:** 1 (chat node only)

**Unchanged fields:** `retrieval_plan`, all context fields, `messages` (not appended on this path)

---

### Memory Update Path

**Example:** `"My name is Alice and I built a todo app in React."`

| Step | Node | State changes |
|------|------|---------------|
| 1 | `intent_router` | Declarative statement → LLM → `route = "memory_update"` |
| 2 | `memory_extractor` | `extracted_profile`, `extracted_semantic` populated |
| 3 | `memory_saver` | Writes JSON + FAISS (side effects only) |
| 4 | `memory_response` | `answer = "Got it! I'll remember that ..."` |
| 5 | `save_history` | Persists Q&A to disk |

**LLM calls:** 1 router (if not pre-routed) + 1 extractor

---

### Research Path (No Tools)

**Example:** `"What's my name?"`

| Step | Node | State changes |
|------|------|---------------|
| 1 | `intent_router` | `route = "research_query"` (question pre-route) |
| 2 | `retrieval_planner` | `retrieval_plan = {profile: true, semantic: false, rag: false}` via heuristics |
| 3 | `memory_retriever` | `profile_context = "=== PROFILE INFORMATION ===\n..."` |
| 4 | `context_builder` | `_combined_context` merged string |
| 5 | `agent` | `answer` set, `messages` appended |
| 6 | `save_history` | History persisted |

If `retrieval_plan` is all false, fan-out skips retrievers and sends state directly to `context_builder`.

---

### Research Path (With Tools)

**Example:** `"What is 157 * 23?"`

| Step | Node | State changes |
|------|------|---------------|
| 1–4 | router → planner → (maybe retrievers) → context | as above |
| 5 | `agent` (iteration 1) | AI message with `tool_calls`; no `answer` yet |
| 6 | `should_continue` | returns `"tools"` |
| 7 | `tools` | Appends `ToolMessage`(s) to `messages` |
| 8 | `agent` (iteration 2) | `answer` set if LLM responds without more tool calls |
| 9 | `should_continue` | returns `"end"` |
| 10 | `save_history` | Persists final answer |

**Loop limit:** Stops after `MAX_TOOL_ITERATIONS` (5) AI messages that contain `tool_calls`.

---

## 4. State Lifecycle

### At graph entry (`ask()`)

All fields initialized explicitly. Prior conversation loaded into `messages` from `CHAT_HISTORY_PATH`.

### During execution

Each node returns a partial dict. LangGraph merges it into state:

- Scalar fields → replaced
- `messages` → merged via `add_messages`

### Branch-specific mutations

| Field | Chat | Memory | Research |
|-------|------|--------|----------|
| `route` | set | set | set |
| `retrieval_plan` | unchanged | unchanged | set by planner |
| `extracted_*` | unchanged | set | unchanged |
| `*_context` | unchanged | unchanged | set by retrievers |
| `_combined_context` | unchanged | unchanged | set by context_builder |
| `answer` | set by chat | set by memory_response | set by agent |
| `messages` | unchanged | unchanged | appended by agent/tools |

### At graph exit

`save_history` writes `question` and final `answer` to JSON. The in-memory `messages` list from the research path is **not** written back to `CHAT_HISTORY_PATH` as structured LangChain messages — only the simple Q&A pair format is persisted.

---

## 5. Tool Loop

### Flow

```
User question
     ↓
  agent  ── builds llm_input (history + context + question), invokes LLM with tools
     ↓
  AIMessage with tool_calls added to messages
     ↓
  should_continue → "tools"
     ↓
  ToolNode executes web_search / calculator
     ↓
  ToolMessage(s) appended to messages (add_messages reducer)
     ↓
  agent again
     ↓
  AIMessage without tool_calls → answer set
     ↓
  save_history
```

### Message accumulation

Each agent invocation appends:

```python
SystemMessage(content=...)
... (prior chat history) ...
HumanMessage(content=question)
AIMessage(content=..., tool_calls=...)  # or final answer
```

`ToolNode` appends one `ToolMessage` per executed tool call.

### Message history integration

The agent correctly builds the prompt by appending the `SystemMessage` to the full `messages` list. Prior `ToolMessage` contents and AI tool calls are perfectly preserved in the conversation, allowing the LLM to correctly reason over multi-step tool workflows (ReAct loop).

---

## 6. Memory Architecture

Four distinct storage mechanisms:

| Store | Location | Format | Written by | Read by |
|-------|----------|--------|------------|---------|
| **Profile memory** | `memory/memory.json` | JSON key-value | `memory_saver` | `memory_retriever` |
| **Semantic memory** | `memory/semantic_memory/` | FAISS index | `memory_saver` | `memory_retriever`, `memory_saver` |
| **RAG documents** | `faiss_index/` | FAISS index | external / manual | `rag_retriever` |
| **Conversation history** | `memory/chat_history.json` | JSON list of `{role, content}` | `save_history` | `load_chat_history()` |

### How they differ

| | Profile | Semantic | RAG | Conversation |
|---|---------|----------|-----|--------------|
| **Content** | Stable identity fields (name, goal, …) | Long-term experiential facts | Company docs | Recent Q&A turns |
| **Structure** | Structured JSON | Vector chunks | Vector chunks | Chronological messages |
| **Retrieval** | Full file read | Similarity search, k=3 | Similarity search, k=3 | Loaded entirely at session start |
| **Update path** | memory_update route | memory_update route | not updated by graph | every graph completion |

### Profile fields supported in extraction schema

`name`, `goal`, `profession`, `education`, `interests`, `favorite_technologies`, `preferences`

---

## 7. Design Decisions

### Why Router, Planner, and Memory Extractor are separate

| Node | Single responsibility |
|------|----------------------|
| Router | Choose workflow branch only |
| Memory Extractor | Parse storable facts from declarative input |
| Retrieval Planner | Choose retrieval sources for questions |

This avoids one monolithic LLM call doing routing + extraction + planning, reduces prompt size, and enforces field ownership.

### Why retrieval is parallel

`fan_out_retrievers()` can dispatch `memory_retriever` and `rag_retriever` concurrently via `Send`. Both write different state fields (`profile_context` / `semantic_context` vs `rag_context`), so they do not conflict. `context_builder` merges results once all branches complete.

### Why memory and RAG are graph nodes, not tools

- Retrieval is **deterministic** and always runs before reasoning on the research path.
- The agent prompt already includes retrieved context in `_combined_context`.
- Keeps tool surface limited to external actions: web search and calculator.
- Prevents the LLM from deciding whether to "call memory" mid-reasoning.

### Why the agent only owns reasoning

Upstream nodes prepare inputs:

- Planner → `retrieval_plan`
- Retrievers → context strings
- Context builder → `_combined_context`

The agent consumes prepared context and decides whether external tools are needed.

---

## 8. Extending the System

### Add a new tool

1. Define the tool in [`nodes/tools.py`](../nodes/tools.py).
2. Append it to the `tools` list.
3. Update `AGENT_SYSTEM_PROMPT` in [`nodes/agent.py`](../nodes/agent.py) with usage guidance.

No changes to router or planner required unless the new capability needs a new route.

### Add a new retriever

1. Add a boolean flag to `retrieval_plan` (requires updating planner prompt/heuristics and `AgentState` docs).
2. Create `nodes/my_retriever.py` returning a new context field.
3. Extend `fan_out_retrievers()` to `Send` the new node.
4. Add an edge from the new node → `context_builder`.
5. Update `context_builder_node` to include the new field in `_combined_context`.

Existing retrievers remain unchanged if the new flag defaults to `false`.

### Add a new route

1. Add route value handling in `intent_router` and `route_from_router()`.
2. Register new nodes and edges in `build_graph()`.
3. Ensure new branch sets `answer` before `save_history`.
4. Add safe defaults in `ask()` initial state for any new fields.

---

## 9. Testing

Tests live in [`tests/test_runtime_fixes.py`](../tests/test_runtime_fixes.py):

| Test | Validates |
|------|-----------|
| `test_agent_node_uses_message_history_in_invoke` | Agent node invoke behavior with prior messages in state |
| `test_save_history_uses_fallback_when_answer_missing` | Empty answer fallback string |
| `test_memory_extractor_node_extracts_profile_and_semantic` | Extractor JSON parsing |
| `test_load_chat_history_restores_previous_turns` | History file loading |

Run:

```bash
python -m unittest discover -s tests -v
```

Requires all dependencies installed in the active environment.

---

## 10. Dependency Notes

[`requirements.txt`](../requirements.txt) lists core packages. Additional runtime imports:

| Package | Used by | In requirements.txt |
|---------|---------|---------------------|
| `asteval` | `calculator` tool | **Yes** |
| `duckduckgo-search`, `ddgs` | `web_search` tool | **Yes** |

Embeddings pull `sentence-transformers` and download model weights on first use.
