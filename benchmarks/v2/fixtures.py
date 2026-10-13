"""Deterministic test fixtures and state isolation for Benchmarks V2.

Provides tenant-isolated relational state seeding and teardown without mutating
legacy mcp_data or memory JSON files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DOCUMENTS_DIR = PROJECT_ROOT / "documents"

# Standard deterministic calendar fixture
DETERMINISTIC_CALENDAR = {
    "events": {
        "evt_101": {
            "title": "Weekly Engineering Sync",
            "date": "2026-10-14",
            "time": "10:00",
            "description": "Team project review and blockers sync",
            "status": "confirmed"
        },
        "evt_102": {
            "title": "Architecture Review",
            "date": "2026-10-14",
            "time": "10:00",
            "description": "Conflict slot with weekly sync",
            "status": "confirmed"
        },
        "evt_103": {
            "title": "Candidate Tech Interview",
            "date": "2026-10-14",
            "time": "11:00",
            "description": "Interview Senior Backend Engineer candidate",
            "status": "confirmed"
        },
        "evt_104": {
            "title": "Executive 1-on-1",
            "date": "2026-10-14",
            "time": "15:00",
            "description": "Quarterly planning and review with VP",
            "status": "confirmed"
        },
        "evt_105": {
            "title": "Cancelled Marketing Sync",
            "date": "2026-10-14",
            "time": "16:00",
            "description": "Cancelled sync",
            "status": "cancelled"
        }
    }
}

# Standard deterministic notes fixture
DETERMINISTIC_NOTES = {
    "notes": {
        "note_101": {
            "title": "Interview Questions",
            "content": "Verify candidate experience in distributed systems, concurrency control, and LangGraph orchestration."
        },
        "note_102": {
            "title": "Executive Presentation Agenda",
            "content": "Review Q3 architecture migration status, latency improvements, and target roadmap."
        },
        "note_103": {
            "title": "Hardware Order Reference",
            "content": "Order #HW-9942 submitted on 2026-10-01 for MacBook Pro 16-inch M3 Max."
        }
    }
}

# Standard deterministic reminders fixture
DETERMINISTIC_REMINDERS = {
    "reminders": {
        "rem_101": {
            "title": "Submit travel expense report",
            "due_date": "2026-10-15 17:00",
            "status": "pending"
        },
        "rem_102": {
            "title": "Confirm interview rubric",
            "due_date": "2026-10-14 09:30",
            "status": "pending"
        }
    }
}

# Standard deterministic profile memory fixture
DETERMINISTIC_MEMORY = {
    "name": "Dr. Alex Vance",
    "role": "Principal AI Systems Architect",
    "location": "Zurich",
    "team": "Autonomous Reasoning Group",
    "primary_language": "Python"
}


def _load_prepared_documents() -> List[Dict[str, Any]]:
    """Load and chunk documents from documents/ directory once in memory."""
    docs = []
    if DOCUMENTS_DIR.exists():
        for p in DOCUMENTS_DIR.glob("*.txt"):
            content = p.read_text(encoding="utf-8", errors="replace")
            paragraphs = [para.strip() for para in content.split("\n\n") if para.strip()]
            chunks = []
            cur_pos = 0
            for idx, para in enumerate(paragraphs):
                chunks.append({
                    "chunk_id": f"{p.stem}_c{idx:03d}",
                    "page_number": 1,
                    "char_start": cur_pos,
                    "char_end": cur_pos + len(para),
                    "content": para,
                    "metadata": {"source": p.name},
                })
                cur_pos += len(para) + 2
            docs.append({
                "stem": p.stem,
                "filename": p.name,
                "content": content,
                "chunks": chunks,
            })
    return docs


_PREPARED_DOCUMENTS = _load_prepared_documents()


def seed_tenant_benchmark_state(user_id: str) -> None:
    """
    Seed clean, tenant-isolated relational state for a single benchmark task.
    Never modifies legacy mcp_data/*.json or memory/memory.json files.
    """
    from datetime import datetime, timezone
    from app.core.context import ExecutionContext
    from app.services.calendar import calendar_service
    from app.knowledge.repository import knowledge_repo
    from app.storage.database import init_db

    init_db()
    ctx = ExecutionContext.create(user_id=user_id)

    # 1. Seed tenant calendar
    calendar_service.seed_events_for_user(user_id, DETERMINISTIC_CALENDAR["events"])

    # 2. Seed tenant profile facts
    for k, v in DETERMINISTIC_MEMORY.items():
        knowledge_repo.set_profile_fact(ctx, key=k, value=str(v))

    # 3. Seed tenant notes
    for nid, n_info in DETERMINISTIC_NOTES["notes"].items():
        knowledge_repo.create_note(ctx, title=n_info["title"], content=n_info["content"], note_id=nid)

    # 4. Seed tenant reminders
    for rid, r_info in DETERMINISTIC_REMINDERS["reminders"].items():
        due_str = r_info["due_date"]
        try:
            due_dt = datetime.fromisoformat(due_str).replace(tzinfo=timezone.utc)
        except Exception:
            try:
                due_dt = datetime.strptime(due_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            except Exception:
                due_dt = datetime.now(timezone.utc)
        knowledge_repo.create_reminder(ctx, title=r_info["title"], due_date=due_dt, reminder_id=rid)

    # 5. Seed tenant documents
    for d in _PREPARED_DOCUMENTS:
        try:
            knowledge_repo.save_document(
                ctx=ctx,
                filename=d["filename"],
                content=d["content"],
                chunks=d["chunks"],
                document_id=f"doc_{d['stem']}",
            )
        except Exception:
            pass


def cleanup_tenant_benchmark_state(user_id: str) -> None:
    """
    Safely tear down all database and memory state for a benchmark tenant.
    Cascade deletes documents, chunks, notes, reminders, facts, and conversation history.
    """
    from app.services.calendar import calendar_service
    from app.storage.database import get_session
    from app.storage.models import UserModel

    calendar_service._user_events.pop(user_id, None)
    with get_session() as session:
        user = session.get(UserModel, user_id)
        if user:
            session.delete(user)


def backup_environment() -> None:
    """No-op in hardened V2 architecture to avoid touching legacy files."""
    pass


def restore_environment() -> None:
    """No-op in hardened V2 architecture to avoid touching legacy files."""
    pass


def reset_to_clean_fixtures() -> None:
    """Reset default tenant state cleanly in relational database without touching legacy files."""
    seed_tenant_benchmark_state("usr_default")
