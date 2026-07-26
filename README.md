# Agentic AI Assistant

A powerful, locally-run AI assistant orchestrated with **LangGraph**. It utilizes a sophisticated StateGraph with **12 specialized nodes** to classify intents, retain long-term profile and semantic memory, perform **hybrid RAG** (FAISS + BM25 + cross-encoder reranking), and execute multi-step tool reasoning workflows (ReAct loop) using Groq's high-speed LLMs.

---

## 🧠 Architecture Overview

The assistant processes each user message through a **directed acyclic graph (DAG)** with three main execution paths determined by intent classification:

```
User Input
    ↓
[intent_router]
    ├──→ chat ──────────────→ save_history ──→ END
    ├──→ memory_extractor → memory_saver → memory_response → save_history ──→ END
    └──→ retrieval_planner → [parallel retrievers] → context_builder → agent ↔ tools → save_history ──→ END
```

### Graph Nodes (12 total)

| Node | Responsibility |
|------|---------------|
| `intent_router` | Classifies input as `chat`, `memory_update`, or `research_query` |
| `chat` | Generates friendly responses for greetings/small talk |
| `memory_extractor` | Extracts profile facts and semantic memories from user statements |
| `memory_saver` | Persists extracted memories to JSON and FAISS index |
| `memory_response` | Generates a confirmation response after saving memory |
| `retrieval_planner` | Decides which retrieval sources are relevant for the question |
| `memory_retriever` | Fetches user profile + semantic memories from local stores |
| `rag_retriever` | Searches company documents using hybrid FAISS + BM25 + reranking |
| `context_builder` | Merges all retrieved contexts into a single prompt |
| `agent` | Core reasoning node — decides when to use tools and generates answers |
| `tools` | Executes web_search and calculator tool calls |
| `save_history` | Persists the Q&A pair to conversation history |

---

## 🌟 Features

### 🧭 Intelligent Intent Routing
Automatically classifies each user message into one of three paths:
- **Chat** — Greetings, small talk, and casual conversation
- **Memory Update** — When the user shares personal facts, preferences, or experiences
- **Research Query** — Everything else: questions, research, requests needing retrieval or tools

Uses a **two-tier approach**: fast Python heuristics (greeting detection, question detection) as a pre-filter, with LLM-based JSON classification as fallback.

### 💾 Persistent Memory System
Four distinct storage mechanisms, each optimized for its purpose:

| Store | Format | Location | Content |
|-------|--------|----------|---------|
| **Profile Memory** | JSON key-value | `memory/memory.json` | Stable identity: name, goal, profession, education, interests, preferences |
| **Semantic Memory** | FAISS vector index | `memory/semantic_memory/` | Long-term experiential memories: projects, courses, experiences |
| **RAG Documents** | FAISS + BM25 + Chunks | `faiss_index/` + `bm25_chunks.pkl` | Company documents, policies, internal knowledge |
| **Conversation History** | JSON message list | `memory/chat_history.json` | Recent Q&A turns (last 100) |

### 📄 Hybrid RAG Retrieval
When answering research queries about company documents, the system uses a **three-stage retrieval pipeline**:

1. **Query Rewriting** — LLM rewrites the user's question into an optimized search query
2. **Dual Retrieval** — Both **FAISS semantic search** (vector embeddings) and **BM25 keyword search** run in parallel
3. **Cross-Encoder Reranking** — A `ms-marco-MiniLM-L6-v2` cross-encoder re-ranks the top candidates for maximum relevance

This hybrid approach ensures high recall (BM25 catches keyword matches) + high precision (FAISS catches semantic similarity) + high relevance (reranker fine-tunes the ordering).

### 🛠️ Multi-Tool Reasoning (ReAct Loop)
The agent can iterate over tools in a reasoning loop:

- **Web Search** — DuckDuckGo integration for current events, news, and external knowledge
- **Calculator** — AST-based math expression evaluator (supports +, -, *, /, **, sqrt, sin, cos, etc.)

The tool loop is **capped at 5 iterations** to prevent infinite loops. The agent decides when to use a tool vs. answer directly based on the retrieved context and its own knowledge.

### 🔄 Parallel Retrieval with Fan-Out
For research queries, the graph dispatches `memory_retriever` and `rag_retriever` **in parallel** using LangGraph's `Send()` API. The `context_builder` node merges results once all branches complete — minimizing latency.

### 🛡️ Self-Healing Tool Calls
The agent includes a **fallback mechanism** for when the LLM generates malformed or hallucinated tool calls. It:
1. Detects the failed generation
2. Parses the intended tool call from the error output
3. Executes the tool directly and feeds the result back to the LLM
4. Falls back to plain reasoning if recovery fails

### 🔁 Complete Chat History
Multi-turn conversations are supported:
- History is loaded at session start from `memory/chat_history.json`
- Each Q&A pair is saved after every graph execution
- The agent sees recent conversation context when generating responses

### 📥 Document Ingestion Pipeline
The `ingest.py` script processes `.txt` documents into the retrieval system:

```
documents/*.txt
    ↓
RecursiveCharacterTextSplitter (chunk_size=800, overlap=150)
    ↓
FAISS index (vector embeddings for semantic search)
    ↓
bm25_chunks.pkl (tokenized chunks for keyword search)
```

Run it with:
```bash
python ingest.py
```

### 🔄 Three Execution Paths in Detail

#### Chat Path
```
Input: "Hello!"
1. intent_router → "chat" (heuristic greeting detection)
2. chat → LLM generates friendly response
3. save_history → persists Q&A
```

#### Memory Update Path
```
Input: "My name is Alice and I'm learning Python"
1. intent_router → "memory_update" (LLM classification)
2. memory_extractor → extracts {name: Alice, interests: [Python]} + semantic memories
3. memory_saver → writes to memory.json + semantic memory FAISS index
4. memory_response → "Got it! I'll remember that your name is Alice..."
5. save_history → persists Q&A
```

#### Research Query Path
```
Input: "What does the company policy say about remote work?"
1. intent_router → "research_query"
2. retrieval_planner → {profile: false, semantic: false, rag: true}
3. [parallel] memory_retriever (skipped) + rag_retriever (executes hybrid search)
4. context_builder → merges RAG results into _combined_context
5. agent → reasons with context, may call tools if needed
6. [loop] tools → agent → tools → ... until answer ready
7. save_history → persists Q&A
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Groq API key ([get one free](https://console.groq.com))

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Vasukumar19/agentic-ai-assistant.git
   cd agentic-ai-assistant
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # Windows
   # source .venv/bin/activate    # Mac/Linux
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your `.env` file:
   ```env
   GROQ_API_KEY=your_key_here
   ```

5. (Optional) Ingest documents for RAG:
   ```bash
   # Place .txt files in the documents/ directory, then run:
   python ingest.py
   ```

6. Run the assistant:
   ```bash
   python agent_langgraph.py
   ```

### Usage Examples

```bash
# Interactive mode
python agent_langgraph.py

# Single question mode
python agent_langgraph.py "What is 144 * 25?"
python agent_langgraph.py "What is the company policy on leave?"
python agent_langgraph.py "Search for latest AI news"
```

---

## 🏗️ Project Structure

```
agent_langGraph/
├── agent_langgraph.py      # Entry point & CLI
├── graph.py                # LangGraph StateGraph builder
├── state.py                # AgentState TypedDict schema
├── config.py               # Paths & model constants
├── llm.py                  # Groq LLM singleton
├── ingest.py               # Document ingestion pipeline
├── reranker.py             # Cross-encoder reranking model
├── requirements.txt        # Python dependencies
│
├── nodes/
│   ├── __init__.py         # Exports all node functions
│   ├── router.py           # Intent classification node
│   ├── chat.py             # Simple chat response node
│   ├── memory_extractor.py # Memory extraction + save + response nodes
│   ├── retrieval_planner.py # Retrieval planning node
│   ├── memory_retriever.py # Profile + semantic memory retrieval
│   ├── rag_retriever.py    # Hybrid RAG retrieval (FAISS + BM25 + rerank)
│   ├── bm25.py             # BM25 keyword search module
│   ├── context_builder.py  # Context merging node
│   ├── agent.py            # Reasoning agent with tool binding
│   ├── tools.py            # Web search & calculator tools
│   └── embeddings.py       # HuggingFace embeddings singleton
│
├── documents/              # Place .txt documents here for ingestion
├── faiss_index/            # Built by ingest.py (FAISS vector index)
├── memory/                 # Created at runtime (profile, semantic, history)
│
└── docs/
    ├── quickstart.md       # Environment setup & troubleshooting
    ├── graphvisual.md      # Architecture & graph flow visuals
    └── implementation.md   # Code-level implementation guide
```

---

## 🧩 Dependencies

| Package | Purpose |
|---------|---------|
| `langchain`, `langchain-core`, `langchain-groq`, `langchain-community`, `langchain-huggingface` | LangChain ecosystem for LLM, tools, embeddings |
| `langgraph` | Workflow orchestration (StateGraph, Send, ToolNode) |
| `sentence-transformers` | Embedding model + cross-encoder reranker |
| `faiss-cpu` | Vector similarity search |
| `groq` | High-speed LLM inference via Groq API |
| `duckduckgo-search`, `ddgs` | Web search tool |
| `asteval` | Safe math expression evaluation |
| `python-dotenv` | Environment variable management |
| `rank-bm25` | Keyword-based retrieval |

---

## 📖 Documentation Reference

- **[Quickstart & Troubleshooting](docs/quickstart.md)** — Environment setup, examples, and common fixes
- **[Architecture & Graph Visuals](docs/graphvisual.md)** — Complete node flow diagrams, edge logic, and state ownership
- **[Implementation Details](docs/implementation.md)** — File-by-file code-level guide with execution flows and design decisions

---

*Built with LangGraph, LangChain, Groq, sentence-transformers, and FAISS.*
