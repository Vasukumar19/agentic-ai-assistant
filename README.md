# Agentic AI Assistant

A powerful, locally-run AI assistant orchestrated with **LangGraph**. It utilizes a sophisticated StateGraph to classify intents, retain long-term conversational and semantic memory, and execute multi-step tool reasoning workflows (ReAct loop) using Groq's high-speed LLMs.

## 🌟 Features

- **🧠 Intelligent Intent Routing:** Automatically distinguishes between casual chat, memory updates, and deep research queries.
- **🛠️ Multi-Tool Reasoning:** Capable of iterating over tools like DuckDuckGo web search and an AST calculator until a problem is solved.
- **💾 Persistent Memory:** Extracts profile facts and semantic memories and stores them locally using JSON and FAISS indices for long-term recall.
- **📄 RAG Document Search:** Ready to retrieve grounded answers from local company documents and codebases (via a pre-built FAISS index).
- **🔁 Complete Chat History:** Context-aware conversations across multi-turn interactions.

## 🚀 Getting Started

To get the assistant running on your local machine, check out the full [Quickstart Guide](docs/quickstart.md).

Here's the brief version:

1. Clone the repository and navigate into it.
2. Create a virtual environment and activate it:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # Windows
   # source .venv/bin/activate    # Mac/Linux
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up your `.env` file with your Groq API key:
   ```env
   GROQ_API_KEY=your_key_here
   ```
5. Run the assistant!
   ```bash
   python agent_langgraph.py
   ```

## 📖 Documentation Reference

Dive deeper into how the graph works and is constructed:

- **[Quickstart & Troubleshooting](docs/quickstart.md):** Environment setup, examples, and fixes.
- **[Architecture & Graph Visuals](docs/graphvisual.md):** Complete node flow, edge logic, and state ownership details.
- **[Implementation Details](docs/implementation.md):** Code-level guide explaining file-by-file logic and memory persistence techniques.

---
*Built with LangGraph, LangChain, and Groq.*
