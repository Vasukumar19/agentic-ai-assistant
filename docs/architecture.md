# Agentic AI Assistant — Production Architecture Specification

## 1. System Overview

The **Agentic AI Assistant** is an enterprise-grade agentic system designed for local-first edge execution using open-weights models (`Qwen3:8b` via Ollama) with seamless cloud failover/upgrades (Claude, GPT-4o, Gemini, Groq).

It unifies:
1. **LangGraph StateGraph** reactive reasoning loop.
2. **Hybrid RAG Pipeline** (Dense FAISS + Sparse BM25 + Reciprocal Rank Fusion + Cross-Encoder Reranking).
3. **Long-Term Memory & User Profiling** (Declarative facts + semantic retrieval).
4. **Model Context Protocol (MCP)** multi-server tool abstraction across 7 servers.
5. **Deterministic Safety Guards** (Goal fulfillment verification, human-in-the-loop confirmation, sandbox boundary isolation).

---

## 2. Complete Architecture Topology

```mermaid
flowchart TD
    User([👤 User Request]) --> TraceInit[0. Trace & Observability Init<br/><code>trace_init_node</code>]
    TraceInit --> Router{1. Intent Router<br/><code>intent_router.py</code>}

    %% Branch A: Conversational
    Router -- "Casual Chat" --> ChatNode[2a. Direct Chat Node<br/><code>chat.py</code>]
    ChatNode --> SaveHistory

    %% Branch B: Memory Extraction
    Router -- "Personal Fact" --> MemExtract[2b. Memory Extractor<br/><code>memory_extractor.py</code>]
    MemExtract --> MemSave[Memory Saver<br/><code>memory_saver_node</code>]
    MemSave --> MemResp[Memory Response<br/><code>memory_response_node</code>]
    MemResp --> SaveHistory

    %% Branch C: Research, RAG & Action Execution
    Router -- "Query / Task / Action" --> RetPlan[2c. Retrieval Planner<br/><code>retrieval_planner.py</code>]

    %% Fan-out Retrieval Subsystem (RAG + Memory)
    subgraph RetrievalSubsystem ["⚡ Parallel Retrieval Subsystem"]
        direction TB
        RetPlan -. "User Context Needed" .-> MemRetriever[Memory Retriever<br/><code>nodes/memory_retriever.py</code>]
        MemRetriever --> ProfileDB[(User Profile & Facts<br/><code>memory/memory.json</code>)]

        RetPlan -. "Knowledge/Doc Query" .-> RAGRetriever[Hybrid RAG Retriever<br/><code>nodes/rag_retriever.py</code>]

        subgraph RAG_Engine ["📚 Hybrid RAG Search Engine"]
            direction TB
            QueryRewrite[Query Rewriter] --> FAISS_Search[(Dense Vector Index<br/><code>faiss_index/</code> MiniLM)]
            QueryRewrite --> BM25_Search[(Sparse Keyword Index<br/><code>bm25_chunks.pkl</code>)]
            FAISS_Search --> RRF[Reciprocal Rank Fusion<br/><code>nodes/rrf.py</code>]
            BM25_Search --> RRF
            RRF --> Reranker[Cross-Encoder Reranker<br/><code>reranker.py</code>]
        end
        RAGRetriever --> RAG_Engine
    end

    %% Convergence
    MemRetriever --> ContextBuilder[3. Context Builder<br/><code>nodes/context_builder.py</code><br/><i>Injects Clock + RAG Docs + Memory</i>]
    Reranker --> ContextBuilder
    RetPlan -- "Direct Action (No Retrieval)" --> ContextBuilder

    %% Reasoning & Action ReAct Loop
    ContextBuilder --> PlannerNode[4. Planner & ReAct Reasoner<br/><code>nodes/planner_node.py</code>]

    subgraph LLM_Provider ["🤖 Multi-LLM Layer (llm.py)"]
        PlannerNode <--> LLMFactory{"get_llm()<br/>Multi-Provider"}
        LLMFactory -. $0 Local .-> Ollama["Ollama (qwen3:8b / llama3)"]
        LLMFactory -. Cloud .-> CloudLLM["Claude 3.5 / GPT-4o / Gemini"]
    end

    PlannerNode --> ToolDecision{Tool Needed?}
    
    ToolDecision -- "Yes (Action Step)" --> ToolNode[5. MCP Tool Executor<br/><code>nodes/tools.py</code>]
    
    %% MCP Tool Layer
    subgraph MCP_Registry ["🛠️ Model Context Protocol (MCP) Server Layer"]
        ToolNode <--> S1["📅 Calendar Server"]
        ToolNode <--> S2["📝 Notes Server"]
        ToolNode <--> S3["⏰ Reminders Server"]
        ToolNode <--> S4["📁 Filesystem Server"]
        ToolNode <--> S5["🐙 GitHub Server"]
        ToolNode <--> S6["🗄️ SQLite Server"]
        ToolNode <--> S7["🌐 Web Fetch Server"]
    end

    ToolNode -- "Tool Results Added to State" --> PlannerNode
    ToolDecision -- "No (Goal Completed / Budget Exhausted)" --> SaveHistory[6. Save History & Trace Persist<br/><code>graph.py</code>]
    SaveHistory --> FinalAnswer([🏁 Formatted Markdown Output])
```

---

## 3. Core Subsystems

### A. State Management (`state.py`)
All execution state is centralized in `AgentState`:
- `question`, `route`, `answer`
- `completed_steps`, `current_step`, `tool_results`, `execution_status`
- `required_operations`, `completed_operations`, `remaining_operations`
- `retrieval_plan`, `retrieved_docs`, `profile_context`
- `trace_events`, `latency_breakdown`, `llm_usage`

### B. Hybrid RAG Subsystem
- **Dense Vector Search**: FAISS vector index using `sentence-transformers/all-MiniLM-L6-v2`.
- **Sparse Lexical Search**: BM25 keyword index over tokenized chunks.
- **Reciprocal Rank Fusion (RRF)**: Merges dense and sparse ranks with \(k=60\) constant.
- **Cross-Encoder Reranking**: `ms-marco-MiniLM-L-6-v2` computes query-document cross-attention relevance scores.

### C. Multi-LLM Layer (`llm.py`)
Unified `get_llm()` factory with plug-and-play provider switching:
- `ollama`: $0 local offline inference (`qwen3:8b`, `llama3`).
- `anthropic`: `claude-3-5-sonnet-20241022`.
- `openai`: `gpt-4o`.
- `google`: `gemini-1.5-pro` / `gemini-2.0-flash`.
- `groq`: Ultra-fast inference with `llama-3.3-70b-versatile`.

### D. Model Context Protocol (MCP) Registry (`mcp_layer/`)
- Unified dynamic discovery and dispatch for 7 MCP stdio servers.
- Parameter auto-healing and JSON schema validation.
- Sandboxed execution with subprocess crash protection.

### E. Deterministic Safety & Policy Engine
1. **Human-in-the-Loop Confirmation**: Destructive operations (`delete_*`, `drop_table`) strictly require human confirmation before execution.
2. **Filesystem Sandboxing**: All file I/O is restricted to `mcp_sandbox/` with path-traversal prevention (`../`).
3. **Loop Detection & Execution Budgets**: Signature-and-result alternating loop detection with a 10-step hard execution budget.
4. **Structured Tracing**: JSONL execution traces persisted in `traces/` with latency metrics.

