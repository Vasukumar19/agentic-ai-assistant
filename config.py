import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env BEFORE reading any env vars below. config may be imported before
# llm.py (e.g. via graph.py), so it must self-load rather than rely on import order.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

PROJECT_ROOT = Path(__file__).resolve().parent
MEMORY_DIR = PROJECT_ROOT / "memory"
SEMANTIC_MEMORY_DIR = MEMORY_DIR / "semantic_memory"
CHAT_HISTORY_PATH = MEMORY_DIR / "chat_history.json"
MEMORY_FILE = MEMORY_DIR / "memory.json"
FAISS_INDEX_DIR = PROJECT_ROOT / "faiss_index"
# Default Model Configuration
MODEL_NAME = "gemini-3.6-flash"
TEMPERATURE = 0.3
MAX_TOOL_STEPS = 5

# LLM Provider Configuration (env-overridable)
# LLM_PROVIDER: google | openrouter | groq | ollama
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()
LLM_MODEL_OVERRIDE = os.getenv("LLM_MODEL", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Phase 2 Config
RETRIEVAL_MODE = "hybrid" # Options: faiss, hybrid, rrf, reranker
RRF_K = 60

# Phase 5 — Observability & Reliability
TRACE_DIR = PROJECT_ROOT / "evaluation" / "traces"
# Timeouts (seconds) — conservative defaults; a single hanging call must not hang the agent
TIMEOUT_LLM_S = float(os.getenv("TIMEOUT_LLM_S", "30"))
TIMEOUT_WEB_SEARCH_S = float(os.getenv("TIMEOUT_WEB_SEARCH_S", "15"))
TIMEOUT_RETRIEVAL_S = float(os.getenv("TIMEOUT_RETRIEVAL_S", "10"))
TIMEOUT_TOOL_S = float(os.getenv("TIMEOUT_TOOL_S", "15"))
# Retry
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "1"))
MAX_TOOL_FAILURES_PER_TOOL = int(os.getenv("MAX_TOOL_FAILURES_PER_TOOL", "3"))

# Phase 6A — MCP
TIMEOUT_MCP_S = float(os.getenv("TIMEOUT_MCP_S", "15"))
MCP_CONFIG_FILE = os.getenv("MCP_CONFIG_FILE", "")
# MCP_SERVERS is a JSON array string or a path; parsed by mcp_layer/registry.py
# Example: '[{"name":"test","transport":"stdio","command":"python","args":["mcp_test_server.py"]}]'
MCP_SERVERS_RAW = os.getenv("MCP_SERVERS", "")

# Phase 7 — Planning strategy experiment (baseline | dependency | replan)
PLANNING_STRATEGY = os.getenv("PLANNING_STRATEGY", "baseline").lower()
MAX_PLAN_STEPS = int(os.getenv("MAX_PLAN_STEPS", "6"))
