# LangGraph Agent — Architecture Reference

This document describes the **actual** LangGraph workflow as implemented in `graph.py` and the node modules under `nodes/`. It reflects the post-refactor architecture where routing, memory extraction, and retrieval planning are separate nodes.

---

## Overall Graph

The compiled graph is built by `build_graph()` in [`graph.py`](../graph.py) and entered through `intent_router`.

```
                              START
                                |
                                v
                        +---------------+
                        | intent_router |
                        +---------------+
                          /     |     \
                         /      |      \
                        v       v       v
                   +------+  +------------------+  +-------------------+
                   | chat |  | memory_extractor |  | retrieval_planner |
                   +------+  +------------------+  +-------------------+
                      |              |                      |
                      |              v                      |
                      |       +--------------+            |
                      |       | memory_saver |            |
                      |       +--------------+            |
                      |              |                      |
                      |              v                      |
                      |     +------------------+            |
                      |     | memory_response  |            |
                      |     +------------------+            |
                      |              |                      |
                      |              |         +-----------+-----------+
                      |              |         | fan_out_retrievers    |
                      |              |         +-----------+-----------+
                      |              |              /    |    \
                      |              |             /     |     \
                      |              |            v      v      v
                      |              |    +-----------+ +-----------+ +-----------------+
                      |              |    | memory_   | | rag_      | | context_builder |
                      |              |    | retriever | | retriever | | (direct skip)   |
                      |              |    +-----------+ +-----------+ +-----------------+
                      |              |            \       /              /
                      |              |             \     /              /
                      |              |              v   v              v
                      |              |           +-----------------+
                      |              |           | context_builder |
                      |              |           +-----------------+
                      |              |                      |
                      |              |                      v
                      |              |                 +-------+
                      |              |                 | agent |
                      |              |                 +-------+
                      |              |                   /     \
                      |              |                  /       \
                      |              |           tool_calls?    no tool_calls
                      |              |                /             \
                      |              |               v               v
                      |              |          +-------+    +-------------+
                      |              |          | tools |    | save_history|
                      |              |          +-------+    +-------------+
                      |              |               |               |
                      |              |               v               v
                      |              |          (back to agent)      END
                      |              |                             
                      v              v                             
                 +-------------+                                   
                 | save_history|                                   
                 +-------------+                                   
                        |                                          
                        v                                          
                       END                                         
```

### Edge Types

| From | To | Type | Condition |
|------|----|------|-----------|
| `START` | `intent_router` | fixed | always |
| `intent_router` | `chat` | conditional | `route == "chat"` |
| `intent_router` | `memory_extractor` | conditional | `route == "memory_update"` |
| `intent_router` | `retrieval_planner` | conditional | `route == "research_query"` (default) |
| `chat` | `save_history` | fixed | always |
| `memory_extractor` | `memory_saver` | fixed | always |
| `memory_saver` | `memory_response` | fixed | always |
| `memory_response` | `save_history` | fixed | always |
| `retrieval_planner` | retrievers / `context_builder` | conditional fan-out | see below |
| `memory_retriever` | `context_builder` | fixed | always |
| `rag_retriever` | `context_builder` | fixed | always |
| `context_builder` | `agent` | fixed | always |
| `agent` | `tools` or `save_history` | conditional | `should_continue()` |
| `tools` | `agent` | fixed | always |
| `save_history` | `END` | fixed | always |

### Fan-Out Retrieval (`fan_out_retrievers`)

Implemented in [`graph.py`](../graph.py) using LangGraph `Send`:

1. If `retrieval_plan.profile` or `retrieval_plan.semantic` is `True` → send to `memory_retriever`.
2. If `retrieval_plan.rag` is `True` → send to `rag_retriever`.
3. If neither applies → send directly to `context_builder` (skip retrieval nodes).

Parallel retriever branches converge at `context_builder`. LangGraph waits for all inbound branches before running `context_builder`.

### Tool Loop

Controlled by `should_continue()` in [`graph.py`](../graph.py):

```
agent  --[last message has tool_calls]-->  tools  -->  agent  -->  ...
agent  --[no tool_calls OR max rounds]-->  save_history
```

- Maximum tool rounds: `MAX_TOOL_ITERATIONS` (5) from [`config.py`](../config.py).
- Tool execution uses LangGraph's prebuilt `ToolNode` from [`nodes/tools.py`](../nodes/tools.py).
- `ToolMessage` objects are appended to `state.messages` via the `add_messages` reducer defined in [`state.py`](../state.py).

### Context Injection (Research Path)

Retrieval happens **once** before the tool loop:

1. `context_builder_node` reads `profile_context`, `semantic_context`, and `rag_context`.
2. It writes `_combined_context` once.
3. `agent_node` reads `_combined_context` from state on each agent invocation and embeds it in a string prompt.

The agent does **not** re-run retrievers during the tool loop. `_combined_context` stays unchanged unless another graph run starts.

**Important implementation detail:** The agent maintains the ReAct loop properly by passing the accumulated `messages` list (including `ToolMessage`s) to the LLM on every iteration, enabling true multi-step tool reasoning.

---

## Node Reference

### `intent_router`

| | |
|---|---|
| **File** | [`nodes/router.py`](../nodes/router.py) |
| **Purpose** | Classify the user message into one of three routes. |
| **Inputs** | `question` |
| **Outputs** | `route` |
| **LLM** | Sometimes (see pre-routing below) |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | No |

**Pre-routing (Python, no LLM):**

| Condition | Route |
|-----------|-------|
| Greeting (`hi`, `hello`, `thanks`, `bye`, `good morning`, `good night`, including prefix forms like `hello there`) | `chat` |
| Obvious question (`?` suffix, or starts with `what`, `why`, `how`, `who`, `where`, `when`, `is`, `are`, `can`, `could`, `does`, `do`) | `research_query` |
| Everything else | LLM classification |

**LLM fallback behavior:**

- Prompt asks for JSON: `{"route": "chat" \| "memory_update" \| "research_query"}`.
- JSON parse failure: retry once.
- Second failure: default to `research_query` (never `chat`).

---

### `chat`

| | |
|---|---|
| **File** | [`nodes/chat.py`](../nodes/chat.py) |
| **Purpose** | Direct conversational reply for greetings and small talk. |
| **Inputs** | `question` |
| **Outputs** | `answer` |
| **LLM** | Yes — `llm.invoke(llm_input)` |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | No |

Reads `messages` to provide conversational context, but does not append to it (history is saved at the end).

---

### `memory_extractor`

| | |
|---|---|
| **File** | [`nodes/memory_extractor.py`](../nodes/memory_extractor.py) |
| **Purpose** | Extract structured profile fields and semantic memory strings from a declarative user statement. |
| **Inputs** | `question` |
| **Outputs** | `extracted_profile`, `extracted_semantic` |
| **LLM** | Yes |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | No |

On JSON parse failure, returns empty profile `{}` and empty semantic list `[]`.

---

### `memory_saver`

| | |
|---|---|
| **File** | [`nodes/memory_extractor.py`](../nodes/memory_extractor.py) |
| **Purpose** | Persist extracted memory to disk. |
| **Inputs** | `extracted_profile`, `extracted_semantic` |
| **Outputs** | `{}` (no state field updates) |
| **LLM** | No |
| **FAISS** | Yes — writes/updates semantic index at `SEMANTIC_MEMORY_DIR` |
| **Filesystem** | Yes — merges profile into `MEMORY_FILE` (`memory/memory.json`) |
| **Tools** | No |

Profile: load JSON → `dict.update()` → save.

Semantic: load existing FAISS index if present, add documents, save locally.

---

### `memory_response`

| | |
|---|---|
| **File** | [`nodes/memory_extractor.py`](../nodes/memory_extractor.py) |
| **Purpose** | Build a templated confirmation string for the user. |
| **Inputs** | `extracted_profile`, `extracted_semantic` |
| **Outputs** | `answer` |
| **LLM** | No |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | No |

Uses deterministic string formatting, not an LLM.

---

### `retrieval_planner`

| | |
|---|---|
| **File** | [`nodes/retrieval_planner.py`](../nodes/retrieval_planner.py) |
| **Function** | `retrieval_planner_node` |
| **Purpose** | Decide which retrieval sources the research path needs. |
| **Inputs** | `question` |
| **Outputs** | `retrieval_plan` → `{profile, semantic, rag}` booleans |
| **LLM** | Sometimes (after heuristics) |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | No |

**Heuristic pass (no LLM):** keyword hints in the normalized question.

| Hint category | Example phrases | Sets |
|---------------|-----------------|------|
| Profile | `my name`, `who am i`, `my goal`, … | `profile: true` |
| Semantic | `projects`, `built`, `courses`, … | `semantic: true` |
| RAG | `company policy`, `procedure`, `policy`, … | `rag: true` |

If no hint matches, calls the LLM. On JSON parse failure, returns all flags `false` (never over-fetch).

> **Note:** There is no `planner.py` file. The planner is implemented as `retrieval_planner_node` in `nodes/retrieval_planner.py`.

---

### `memory_retriever`

| | |
|---|---|
| **File** | [`nodes/memory_retriever.py`](../nodes/memory_retriever.py) |
| **Purpose** | Load profile JSON and/or search semantic memory. |
| **Inputs** | `question`, `retrieval_plan` |
| **Outputs** | `profile_context`, `semantic_context` |
| **LLM** | No |
| **FAISS** | Yes — semantic search at `SEMANTIC_MEMORY_DIR`, `k=3` |
| **Filesystem** | Yes — reads `MEMORY_FILE` |
| **Tools** | No |

Returns empty strings for sources not requested or not found.

---

### `rag_retriever`

| | |
|---|---|
| **File** | [`nodes/rag_retriever.py`](../nodes/rag_retriever.py) |
| **Purpose** | Search pre-built company document index using hybrid retrieval. |
| **Inputs** | `question`, `retrieval_plan` |
| **Outputs** | `rag_context` |
| **LLM** | No |
| **FAISS** | Yes — search at `FAISS_INDEX_DIR`, `k=20` |
| **BM25** | Yes — keyword search in parallel with FAISS |
| **Reranker** | Yes — cross-encoder re-ranks top 20 candidates to top 5 |
| **Filesystem** | No (reads FAISS index only) |
| **Tools** | No |

**Hybrid RAG Pipeline:**

1. **Query Rewriting** — LLM rewrites the user's question into an optimized search query via `rewrite_prompt`
2. **Dual Retrieval** — Both FAISS semantic search (`similarity_search_with_score`, k=20) and BM25 keyword search (`bm25_search`, k=20) run in parallel
3. **Merge & Filter** — Results are merged by `chunk_id`. FAISS results with score > 0.8 threshold are dropped. BM25 results are always included
4. **Cross-Encoder Reranking** — `cross-encoder/ms-marco-MiniLM-L6-v2` re-ranks up to 20 candidates, returns top 5
5. **Formatting** — Results are labeled with source filename, page number, retriever type, and relevance score

If `retrieval_plan.rag` is `false`, returns `{"rag_context": ""}` immediately.

If `FAISS_INDEX_DIR` does not exist, logs a message and returns empty context.

---

### `bm25` (Helper Module)

| | |
|---|---|
| **File** | [`nodes/bm25.py`](../nodes/bm25.py) |
| **Purpose** | BM25 keyword-based retrieval for hybrid search. |
| **Exports** | `bm25_search(query, k=5)` |
| **Storage** | Pickled document chunks in `bm25_chunks.pkl` (created by `ingest.py`) |
| **Dependencies** | `rank-bm25`, tokenized with regex `\w+` |

Lazily loads the BM25 index on first call. Used by `rag_retriever_node` to supplement FAISS semantic search.

---

### `reranker` (Helper Module)

| | |
|---|---|
| **File** | [`reranker.py`](../reranker.py) |
| **Purpose** | Cross-encoder reranking for RAG results. |
| **Exports** | `rerank(query, items, top_k=5)` |
| **Model** | `cross-encoder/ms-marco-MiniLM-L6-v2` via `sentence-transformers` |

Takes query + candidate documents, computes relevance scores via cross-encoder, returns top-k re-ranked results. Improves precision over pure embedding similarity.

---

### `context_builder`

| | |
|---|---|
| **File** | [`nodes/context_builder.py`](../nodes/context_builder.py) |
| **Purpose** | Merge retrieval outputs into one prompt block. |
| **Inputs** | `profile_context`, `semantic_context`, `rag_context` |
| **Outputs** | `_combined_context` |
| **LLM** | No |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | No |

Joins non-empty sections with `\n\n`. If all inputs are empty, `_combined_context` is `""`.

---

### `agent`

| | |
|---|---|
| **File** | [`nodes/agent.py`](../nodes/agent.py) |
| **Purpose** | Reason over retrieved context and optionally call tools. |
| **Inputs** | `question`, `_combined_context`, `messages` |
| **Outputs** | `messages` always; `answer` when no tool calls |
| **LLM** | Yes — `llm.bind_tools(tools).invoke(llm_input)` |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | Binds `web_search` and `calculator` |

Reads `messages` history and appends the new `AIMessage(..., tool_calls=...)` or final answer on each invocation.

---

### `tools`

| | |
|---|---|
| **File** | [`nodes/tools.py`](../nodes/tools.py) |
| **Purpose** | Execute tool calls from the last AI message. |
| **Inputs** | `messages` (must end with AI message containing `tool_calls`) |
| **Outputs** | Appends `ToolMessage`(s) to `messages` |
| **LLM** | No |
| **FAISS** | No |
| **Filesystem** | No |
| **Tools** | Executes `web_search`, `calculator` |

Implemented as LangGraph `ToolNode(tools)`.

---

### `save_history`

| | |
|---|---|
| **File** | [`graph.py`](../graph.py) — `save_history_node` |
| **Purpose** | Persist the Q&A pair to conversation history. |
| **Inputs** | `question`, `answer` |
| **Outputs** | `{}` |
| **LLM** | No |
| **FAISS** | No |
| **Filesystem** | Yes — `CHAT_HISTORY_PATH` (`memory/chat_history.json`) |
| **Tools** | No |

Fallback answer when `answer` is empty:

```
I wasn't able to complete the request after several tool attempts.
```

Caps file to the last **100 JSON entries** (not 100 pairs — each turn adds 2 entries).

---

## State Ownership

Each field has a single producer during a graph run:

| Field | Produced By | Notes |
|-------|-------------|-------|
| `question` | `agent_langgraph.ask()` | Set in initial state; unchanged during run |
| `route` | `intent_router` | |
| `retrieval_plan` | `retrieval_planner` | Safe default in initial state: all `false` |
| `extracted_profile` | `memory_extractor` | Safe default: `{}` |
| `extracted_semantic` | `memory_extractor` | Safe default: `[]` |
| `profile_context` | `memory_retriever` | Safe default: `""` |
| `semantic_context` | `memory_retriever` | Safe default: `""` |
| `rag_context` | `rag_retriever` | Safe default: `""` |
| `_combined_context` | `context_builder` | Safe default: `""` |
| `answer` | `chat`, `agent`, or `memory_response` | Whichever terminal node on the active branch |
| `messages` | `agent`, `tools` (`ToolNode`) | Loaded at start from chat history; appended on research/tool path |

Nodes should not overwrite fields owned by other nodes. The chat and memory branches never run planner or extractor, so they rely on initial-state defaults for unused fields.

---

## Performance Comparison

Approximate work per path (single user turn):

| Path | Nodes executed | Typical LLM calls | FAISS | Filesystem | Tools |
|------|----------------|-------------------|-------|------------|-------|
| **Chat** | router → chat → save_history | 0–1 (0 if pre-routed greeting) | No | save history only | No |
| **Memory update** | router → extractor → saver → response → save_history | 1–3 (router LLM only if not pre-routed) | write semantic index | read/write memory JSON | No |
| **Research (no tools)** | router → planner → retrievers → context → agent → save_history | 1–3 + 1 agent | maybe read | save history | No |
| **Research (with tools)** | same + agent ↔ tools loop | +1 per agent iteration (max 5 tool rounds) | maybe read | save history | 1+ tool executions |

### Where LLM calls occur

| Node | When |
|------|------|
| `intent_router` | Ambiguous declarative messages only |
| `chat` | Always (after routing to chat) |
| `memory_extractor` | Always on memory_update path |
| `retrieval_planner` | When heuristics cannot decide |
| `agent` | Every agent loop iteration on research path |

Shared LLM instance: [`llm.py`](../llm.py) — single `ChatGroq` for the entire project.

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Router JSON fails twice | Route defaults to `research_query` |
| Planner JSON fails | `retrieval_plan` all `false` → skip retrievers, go to `context_builder` |
| Memory extractor JSON fails | Empty extraction; saver may no-op; response still generated |
| `memory.json` missing | Profile retrieval returns empty string |
| Semantic FAISS missing | Semantic retrieval skipped; warning logged on save/load errors |
| `faiss_index/` missing | RAG returns empty context; agent proceeds without document context |
| Max tool iterations reached | Graph stops tool loop even if last AI message still has `tool_calls` |
| Empty `answer` at save | Fallback string written to history |
| Declarative personal statement | Pre-routing skips LLM question detection; router LLM may return `memory_update` |
| Question with greeting prefix | `"hello, what is my name?"` → pre-routed to `chat` because greeting matches first |

---

## Related Files

| File | Role |
|------|------|
| [`graph.py`](../graph.py) | Graph construction, routing helpers, save history |
| [`state.py`](../state.py) | `AgentState` TypedDict |
| [`config.py`](../config.py) | Paths and constants |
| [`llm.py`](../llm.py) | Shared Groq LLM singleton |
| [`agent_langgraph.py`](../agent_langgraph.py) | CLI entry point, initial state, history loading |
