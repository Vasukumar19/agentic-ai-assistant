"""Centralized V2 Configuration & Secrets Management using Pydantic Settings."""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Production settings schema with strict validation and sane defaults."""

    # Project Environment
    ENVIRONMENT: str = "development"  # development | production | testing
    AUTH_MODE: str = "development"    # development | production | testing
    AUTH_API_KEYS: List[str] = Field(default_factory=list)

    # Project Paths
    PROJECT_ROOT: Path = PROJECT_ROOT
    STORAGE_DIR: Path = PROJECT_ROOT / "storage"
    DATA_DIR: Path = PROJECT_ROOT / "storage" / "data"
    SECRETS_DIR: Path = PROJECT_ROOT / "storage" / "secrets"
    TRACES_DIR: Path = PROJECT_ROOT / "traces"

    # Database
    DATABASE_URL: str = Field(
        default=f"sqlite:///{PROJECT_ROOT / 'storage' / 'agentic_v2.db'}",
        description="SQLAlchemy database connection URI (SQLite WAL mode for local-first single-instance storage)",
    )

    # CORS Configuration
    CORS_ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"],
        description="Explicit allowlist of origins for CORS. Wildcard origins are rejected in production.",
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
    APPROVAL_HMAC_SECRET: Optional[str] = Field(
        default=None,
        description="Secret key for signing HMAC approval tokens (min 32 chars required in production)",
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

    def get_approval_hmac_secret(self) -> str:
        """
        Retrieve validated HMAC signing secret.
        Fails closed in production if secret is missing or insecure (< 32 chars).
        In development/testing, generates a high-entropy local secret if none is configured.
        """
        secret = self.APPROVAL_HMAC_SECRET
        if secret and len(secret) >= 32:
            return secret

        if self.ENVIRONMENT == "production":
            raise ValueError(
                "Insecure configuration: APPROVAL_HMAC_SECRET must be at least 32 characters in production. "
                "Refusing application startup."
            )

        # Local development / testing mode: persist or generate high-entropy secret
        secret_file = self.SECRETS_DIR / "dev_approval_hmac.key"
        if secret_file.exists():
            stored = secret_file.read_text(encoding="utf-8").strip()
            if len(stored) >= 32:
                return stored

        # Generate fresh 256-bit entropy
        new_secret = secrets.token_hex(32)
        try:
            secret_file.write_text(new_secret, encoding="utf-8")
        except Exception as e:
            logger.warning("Could not persist local dev secret key: %s", e)
        return new_secret

    def validate_security_configuration(self) -> None:
        """Perform startup security assertions."""
        if self.ENVIRONMENT == "production":
            if not self.APPROVAL_HMAC_SECRET or len(self.APPROVAL_HMAC_SECRET) < 32:
                raise ValueError(
                    "Production security failure: APPROVAL_HMAC_SECRET must be explicitly set and >= 32 characters."
                )
            if "*" in self.CORS_ALLOWED_ORIGINS:
                raise ValueError(
                    "Production security failure: Wildcard CORS origin '*' is strictly prohibited with credentials."
                )


# Global singleton instance
settings = Settings()
settings.ensure_directories()
