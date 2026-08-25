import os
from pathlib import Path

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
