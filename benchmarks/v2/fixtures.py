"""Deterministic test fixtures and state isolation for Benchmarks V2."""

import json
import shutil
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

MCP_DATA_DIR = PROJECT_ROOT / "mcp_data"
MEMORY_DIR = PROJECT_ROOT / "memory"
SANDBOX_DIR = PROJECT_ROOT / "mcp_sandbox"

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

_BACKUP_STORAGE = {}


def backup_environment():
    """Backup active files before running benchmark suite."""
    MCP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    files_to_backup = [
        MCP_DATA_DIR / "calendar.json",
        MCP_DATA_DIR / "notes.json",
        MCP_DATA_DIR / "reminders.json",
        MEMORY_DIR / "memory.json",
    ]

    for p in files_to_backup:
        if p.exists():
            try:
                _BACKUP_STORAGE[str(p)] = p.read_text(encoding="utf-8")
            except Exception:
                pass


def restore_environment():
    """Restore active files after benchmark suite finishes."""
    for path_str, content in _BACKUP_STORAGE.items():
        try:
            Path(path_str).write_text(content, encoding="utf-8")
        except Exception:
            pass


def reset_to_clean_fixtures():
    """Reset calendar, notes, reminders, and profile memory to clean deterministic state."""
    MCP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    (MCP_DATA_DIR / "calendar.json").write_text(json.dumps(DETERMINISTIC_CALENDAR, indent=2), encoding="utf-8")
    (MCP_DATA_DIR / "notes.json").write_text(json.dumps(DETERMINISTIC_NOTES, indent=2), encoding="utf-8")
    (MCP_DATA_DIR / "reminders.json").write_text(json.dumps(DETERMINISTIC_REMINDERS, indent=2), encoding="utf-8")
    (MEMORY_DIR / "memory.json").write_text(json.dumps(DETERMINISTIC_MEMORY, indent=2), encoding="utf-8")

    try:
        from scripts.migrate_v1_data import migrate_all_v1_data
        migrate_all_v1_data(target_user_id="usr_default")
    except Exception:
        pass
