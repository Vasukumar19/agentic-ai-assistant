"""Centralized V2 Configuration & Secrets Management using Pydantic Settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Production settings schema with strict validation and sane defaults."""

    # Project Paths
    PROJECT_ROOT: Path = PROJECT_ROOT
    STORAGE_DIR: Path = PROJECT_ROOT / "storage"
    DATA_DIR: Path = PROJECT_ROOT / "storage" / "data"
    SECRETS_DIR: Path = PROJECT_ROOT / "storage" / "secrets"
    TRACES_DIR: Path = PROJECT_ROOT / "traces"

    # Database
    DATABASE_URL: str = Field(
        default=f"sqlite:///{PROJECT_ROOT / 'storage' / 'agentic_v2.db'}",
        description="SQLAlchemy database connection URI (SQLite or PostgreSQL with pgvector)",
    )

    # LLM Settings
    LLM_PROVIDER: str = "ollama"  # ollama | anthropic | openai | google | groq
    LLM_MODEL: str = "qwen3:8b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_REASONING: int = 0

    # Operational Timeouts & Budgets
    TIMEOUT_LLM_S: int = 120
    TIMEOUT_RETRIEVAL_S: int = 15
    TIMEOUT_TOOL_S: int = 30
    MAX_EXECUTION_STEPS: int = 10
    CONTEXT_TOKEN_BUDGET: int = 3500

    # Security & Approval Secrets
    APPROVAL_HMAC_SECRET: str = Field(
        default="v2_dev_secret_key_change_in_production_394812",
        description="Secret key for signing HMAC approval tokens",
    )
    APPROVAL_EXPIRATION_SECONDS: int = 3600  # 1 hour

    # Integrations (Google Calendar)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_CREDENTIALS_FILE: Optional[str] = None
    GOOGLE_TOKEN_FILE: Optional[str] = ".google_token.json"

    # RAG & Embeddings
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    CROSS_ENCODER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_directories(self) -> None:
        """Create standard storage and trace directories if they do not exist."""
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        self.TRACES_DIR.mkdir(parents=True, exist_ok=True)


# Global singleton instance
settings = Settings()
settings.ensure_directories()
