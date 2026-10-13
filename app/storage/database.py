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


def init_db() -> None:
    """Initialize all database tables defined in models."""
    import app.storage.models  # noqa: F401 - ensures models are registered on Base
    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
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
