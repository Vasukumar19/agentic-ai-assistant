import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env BEFORE reading any env vars below.
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
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:8b")
LLM_MODEL_OVERRIDE = LLM_MODEL
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Phase 2 Config
RETRIEVAL_MODE = "hybrid"  # Options: faiss, hybrid, rrf, reranker
RRF_K = 60

# Phase 5 — Observability & Reliability
TRACE_DIR = PROJECT_ROOT / "evaluation" / "traces"
TIMEOUT_LLM_S = float(os.getenv("TIMEOUT_LLM_S", "30"))
TIMEOUT_WEB_SEARCH_S = float(os.getenv("TIMEOUT_WEB_SEARCH_S", "15"))
TIMEOUT_RETRIEVAL_S = float(os.getenv("TIMEOUT_RETRIEVAL_S", "10"))
TIMEOUT_TOOL_S = float(os.getenv("TIMEOUT_TOOL_S", "15"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "1"))
MAX_TOOL_FAILURES_PER_TOOL = int(os.getenv("MAX_TOOL_FAILURES_PER_TOOL", "3"))

# Phase 8 — execution budget
MAX_EXECUTION_STEPS = int(os.getenv("MAX_EXECUTION_STEPS", "10"))

# Phase 6A — MCP
TIMEOUT_MCP_S = float(os.getenv("TIMEOUT_MCP_S", "15"))
MCP_CONFIG_FILE = os.getenv("MCP_CONFIG_FILE", "")
MCP_SERVERS_RAW = os.getenv("MCP_SERVERS", "")

# Phase 7 — Planning strategy (default: hybrid)
PLANNING_STRATEGY = os.getenv("PLANNING_STRATEGY", "hybrid").lower()
MAX_PLAN_STEPS = int(os.getenv("MAX_PLAN_STEPS", "10"))

# Phase 7B — Hybrid adaptive planner
MAX_REPLANS = int(os.getenv("MAX_REPLANS", "1"))
HYBRID_LEVEL_CAP = int(os.getenv("HYBRID_LEVEL_CAP", "2"))
HYBRID_REPLAN = os.getenv("HYBRID_REPLAN", "1").lower() not in ("0", "false", "no")

# Phase 11 & Phase 12 — Result-Aware Replanning & Completion Context (default: on)
RESULT_AWARE_REPLANNING = os.getenv("RESULT_AWARE_REPLANNING", "on").lower()
COMPLETION_GUARD = os.getenv("COMPLETION_GUARD", "on").lower()
PLANNER_COMPLETION_CONTEXT = os.getenv("PLANNER_COMPLETION_CONTEXT", "on").lower()

# Phase 13 — Goal Fulfillment & MCP Reliability (default: on)
GOAL_FULFILLMENT_GUARD = os.getenv("GOAL_FULFILLMENT_GUARD", "on").lower()
MCP_ARGUMENT_REPAIR = os.getenv("MCP_ARGUMENT_REPAIR", "on").lower()
MAX_ARGUMENT_REPAIR_ATTEMPTS = int(os.getenv("MAX_ARGUMENT_REPAIR_ATTEMPTS", "1"))
