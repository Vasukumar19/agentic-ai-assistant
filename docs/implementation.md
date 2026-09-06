# LangGraph Agentic AI Assistant — Implementation Guide

This guide explains how the Agentic AI Assistant is implemented. All descriptions are derived directly from the active source code.

---

## 1. Project Overview

### What this project is

A production-grade Python agent that routes each user message through a **LangGraph `StateGraph`**. Depending on intent, it either:

- replies directly (`chat`),
- extracts and stores personal memory facts (`memory_update`), or
- plans retrieval, gathers context, performs Hybrid RAG, reasons, and executes multi-step actions across 7 **Model Context Protocol (MCP)** servers (`research_query`).

### Core concepts

| Concept | Implementation |
|---------|----------------|
| **LangGraph** | Workflow orchestration library (`langgraph`) |
| **StateGraph** | Built in [`graph.py`](../graph.py) with typed state [`AgentState`](../state.py) |
| **Multi-LLM Engine** | Unified provider factory in [`llm.py`](../llm.py) (Ollama $0 local, Claude, GPT-4o, Gemini, Groq) |
| **Hybrid RAG** | Dense FAISS + Sparse BM25 + Reciprocal Rank Fusion + Cross-Encoder Reranking in [`nodes/rag_retriever.py`](../nodes/rag_retriever.py) |
| **Model Context Protocol** | Dynamic multi-server registry in [`mcp_layer/`](../mcp_layer/) across 7 servers |
| **ReAct Planning Node** | Dynamic reasoning, goal fulfillment verification, and parameter repair in [`nodes/planner_node.py`](../nodes/planner_node.py) |
| **Observability** | Structured JSONL tracing in `traces/` with latency breakdowns in [`observability/`](../observability/) |

---

## 2. File Reference

### [`main.py`](../main.py)

| | |
|---|---|
| **Purpose** | Application entry point, interactive shell, and one-command runner |
| **Responsibilities** | Check Ollama connectivity, discover MCP servers, compile LangGraph, run multi-turn queries, format rich Markdown outputs |
| **Key functions** | `check_ollama()`, `init_mcp()`, `run_query()`, `interactive_loop()`, `main()` |
| **Inputs** | User string via interactive prompt or CLI arguments |
| **Outputs** | Formatted Markdown responses; persisted traces and chat history |
| **Dependencies** | `graph`, `state`, `config`, `llm`, `mcp_layer.registry` |

**Startup sequence:**

1. `load_dotenv()`
2. Check Ollama connectivity / Cloud API configuration
3. `registry.discover()` to initialize all 7 MCP servers
4. `create_runnable_graph()` with checkpointing
5. Interactive shell with streaming output

---

### [`graph.py`](../graph.py)

| | |
|---|---|
| **Purpose** | Construct and compile the LangGraph workflow |
| **Responsibilities** | Register nodes/edges, routing helpers, save history, execution budget circuit breakers |
| **Key functions** | `build_graph()`, `create_runnable_graph()`, `route_from_router()`, `fan_out_retrievers()`, `should_continue()`, `save_history_node()` |
| **Inputs** | `AgentState` dict per invocation |
| **Outputs** | Compiled runnable graph; terminal state after invoke |
| **Dependencies** | `langgraph`, `state`, `config`, all node functions |

**Graph node names (LangGraph registry):**

| Registered name | Function |
|-----------------|----------|
| `trace_init` | `trace_init_node` |
| `intent_router` | `intent_router` |
| `chat` | `chat_node` |
| `memory_extractor` | `memory_extractor_node` |
| `memory_saver` | `memory_saver_node` |
| `memory_response` | `memory_response_node` |
| `retrieval_planner` | `retrieval_planner_node` |
| `memory_retriever` | `memory_retriever_node` |
| `rag_retriever` | `rag_retriever_node` |
| `context_builder` | `context_builder_node` |
| `planner` | `planner_node` |
| `tools` | `tool_node` |
| `save_history` | `save_history_node` |

---

### [`state.py`](../state.py)

| | |
|---|---|
| **Purpose** | Define the graph state schema |
| **Responsibilities** | TypedDict for complete graph state |
| **Key type** | `AgentState` |
| **Dependencies** | `typing`, `langchain_core.messages`, `langgraph.graph.message.add_messages` |

---

### [`config.py`](../config.py)

| | |
|---|---|
| **Purpose** | Centralized constants, environment settings, and filesystem paths |
| **Responsibilities** | Single source of truth for paths, model settings, and budgets |
| **Dependencies** | `pathlib.Path`, `dotenv` |

| Setting | Default Value | Purpose |
|---------|---------------|---------|
| `LLM_PROVIDER` | `"ollama"` | Active LLM provider (`ollama`, `anthropic`, `openai`, `google`, `groq`) |
| `LLM_MODEL` | `"qwen3:8b"` | Model identifier |
| `OLLAMA_BASE_URL` | `"http://localhost:11434"` | Local Ollama endpoint |
| `MAX_EXECUTION_STEPS`| `10` | Hard cap on ReAct tool iterations |
| `RETRIEVAL_MODE` | `"hybrid"` | RAG search strategy (`hybrid`, `faiss`, `rrf`, `reranker`) |
| `RRF_K` | `60` | Reciprocal Rank Fusion smoothing constant |
| `TRACE_DIR` | `PROJECT_ROOT / "traces"` | JSONL trace storage directory |

---

### [`llm.py`](../llm.py)

| | |
|---|---|
| **Purpose** | Multi-provider LLM factory |
| **Responsibilities** | Instantiate the active chat model based on `LLM_PROVIDER` |
| **Key functions** | `get_llm(provider, model_name)` |
| **Supported Providers** | Ollama (`ChatOllama`), Anthropic (`ChatAnthropic`), OpenAI (`ChatOpenAI`), Google (`ChatGoogleGenerativeAI`), Groq (`ChatGroq`) |

---

### [`nodes/router.py`](../nodes/router.py)

| | |
|---|---|
| **Purpose** | Intent classification |
| **Function** | `intent_router(state)` |
| **Inputs** | `question` |
| **Outputs** | `route` (`chat`, `memory_update`, `research_query`) |
| **Dependencies** | `llm` |

---

### [`nodes/chat.py`](../nodes/chat.py)

| | |
|---|---|
| **Purpose** | Conversational small-talk responses |
| **Function** | `chat_node(state)` |
| **Inputs** | `question`, `messages` |
| **Outputs** | `answer` |
| **Dependencies** | `llm` |

---

### [`nodes/memory_extractor.py`](../nodes/memory_extractor.py)

Contains three pipeline node functions:
- `memory_extractor_node`: Extracts profile facts and semantic memories via JSON prompt.
- `memory_saver_node`: Persists profile to `memory/memory.json` and updates FAISS index in `memory/semantic_memory/`.
- `memory_response_node`: Produces confirmation message to the user.

---

### [`nodes/retrieval_planner.py`](../nodes/retrieval_planner.py)

| | |
|---|---|
| **Purpose** | Route queries to profile memory, semantic memory, or RAG documents |
| **Function** | `retrieval_planner_node(state)` |
| **Outputs** | `retrieval_plan` dict (`{"profile": bool, "semantic": bool, "rag": bool}`) |

---

### [`nodes/rag_retriever.py`](../nodes/rag_retriever.py)

| | |
|---|---|
| **Purpose** | Hybrid RAG search engine over company knowledge base |
| **Function** | `rag_retriever_node(state)` |
| **Pipeline** | Query rewriting $\rightarrow$ FAISS vector search + BM25 keyword search $\rightarrow$ Reciprocal Rank Fusion $\rightarrow$ Cross-encoder reranking |
| **Dependencies** | `embeddings`, `bm25`, `rrf`, `reranker` |

---

### [`nodes/context_builder.py`](../nodes/context_builder.py)

| | |
|---|---|
| **Purpose** | Assemble dynamic prompt context |
| **Function** | `context_builder_node(state)` |
| **Injected Data** | Real-time timestamp/clock, user profile facts, semantic memories, and retrieved document passages |

---

### [`nodes/planner_node.py`](../nodes/planner_node.py)

| | |
|---|---|
| **Purpose** | ReAct reasoning engine, multi-step orchestration, goal fulfillment guard, and parameter auto-healing |
| **Function** | `planner_node(state)` |
| **Key Features** | Compact workflow progress summary, parameter repair, loop detection, formatting synthesis rules |

---

### [`nodes/tools.py`](../nodes/tools.py) & MCP Multi-Server Layer

| | |
|---|---|
| **Purpose** | Execute native tools and 7 Model Context Protocol (MCP) servers |
| **Servers** | `calendar`, `notes`, `reminders`, `filesystem`, `github`, `sqlite`, `fetch` |
| **Safety** | Human-in-the-loop confirmation for destructive actions, `mcp_sandbox/` jail for file operations |

---

## 3. Testing & Verification

Automated test suites live under [`tests/`](../tests/):

- **Integration Tests** (`tests/integration/test_real_app_mcp.py`): Validates multi-server discovery, GitHub, SQLite, and Web Fetch data flow.
- **Security Tests** (`tests/security/test_real_app_security.py`): Validates human confirmation enforcement, URL scheme restrictions, and secret redaction.
- **One-Command Smoke Test** (`scripts/smoke_test.py`): Rapid 9-point verification of Ollama, MCP registry, filesystem sandboxing, and graph execution.
