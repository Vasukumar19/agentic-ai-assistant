from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
MEMORY_DIR = PROJECT_ROOT / "memory"
SEMANTIC_MEMORY_DIR = MEMORY_DIR / "semantic_memory"
CHAT_HISTORY_PATH = MEMORY_DIR / "chat_history.json"
MEMORY_FILE = MEMORY_DIR / "memory.json"
FAISS_INDEX_DIR = PROJECT_ROOT / "faiss_index"
# MODEL_NAME = "llama-3.1-8b-instant"
MODEL_NAME = "openai/gpt-oss-120b"
TEMPERATURE = 0.3
MAX_TOOL_ITERATIONS = 5

# Phase 2 Config
RETRIEVAL_MODE = "faiss" # Options: faiss, hybrid, rrf, reranker
RRF_K = 60
