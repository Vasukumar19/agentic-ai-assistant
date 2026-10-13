"""SQLAlchemy database engine, session management, and SQLite optimizations."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.engine import Engine

from app.core.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# Connection arguments for SQLite optimizations
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 15.0}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and foreign key enforcement on SQLite connections."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    except Exception as e:
        logger.debug("Non-sqlite or pragma failure: %s", e)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _run_schema_migrations(eng: Engine) -> None:
    """Safely apply schema migrations for any added columns to existing tables."""
    from sqlalchemy import inspect, text
    with eng.connect() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()

        if "action_approvals" in tables:
            cols = {c["name"] for c in inspector.get_columns("action_approvals")}
            if "risk_level" not in cols:
                conn.execute(text("ALTER TABLE action_approvals ADD COLUMN risk_level VARCHAR(32) DEFAULT 'DESTRUCTIVE'"))
            if "executed_at" not in cols:
                conn.execute(text("ALTER TABLE action_approvals ADD COLUMN executed_at DATETIME"))
            if "execution_outcome" not in cols:
                conn.execute(text("ALTER TABLE action_approvals ADD COLUMN execution_outcome TEXT"))

        if "reminders" in tables:
            cols = {c["name"] for c in inspector.get_columns("reminders")}
            if "delivery_attempts" not in cols:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN delivery_attempts INTEGER DEFAULT 0"))
            if "last_attempt_at" not in cols:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN last_attempt_at DATETIME"))
            if "delivery_error" not in cols:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN delivery_error TEXT"))

        conn.commit()


def init_db() -> None:
    """Initialize all database tables defined in models with versioned schema migrations."""
    import app.storage.models  # noqa: F401 - ensures models are registered on Base
    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
    _run_schema_migrations(engine)
    logger.info("Initialized database schema at %s", settings.DATABASE_URL)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
