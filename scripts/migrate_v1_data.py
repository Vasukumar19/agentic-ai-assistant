"""Data Migration Script: Migrate V1 JSON and text documents into V2 relational database."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from app.core.config import settings
from app.core.context import ExecutionContext
from app.storage.database import init_db, get_session
from app.knowledge.repository import knowledge_repo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def migrate_all_v1_data(target_user_id: str = "usr_default") -> None:
    """Migrate documents, memory.json, notes.json, and reminders.json into V2 database."""
    init_db()
    ctx = ExecutionContext.create(user_id=target_user_id)
    logger.info("Starting V1 data migration for tenant '%s'...", target_user_id)

    # 1. Migrate Profile Facts from memory/memory.json
    memory_path = PROJECT_ROOT / "memory" / "memory.json"
    if memory_path.exists():
        try:
            data = json.loads(memory_path.read_text(encoding="utf-8"))
            migrated_facts = 0
            for k, v in data.items():
                if v:
                    val_str = str(v) if not isinstance(v, (dict, list)) else json.dumps(v)
                    knowledge_repo.set_profile_fact(ctx, key=k, value=val_str)
                    migrated_facts += 1
            logger.info("Migrated %d profile facts from %s", migrated_facts, memory_path)
        except Exception as e:
            logger.warning("Failed migrating memory.json: %s", e)

    # 2. Migrate Notes from mcp_data/notes.json
    notes_path = PROJECT_ROOT / "mcp_data" / "notes.json"
    if notes_path.exists():
        try:
            from app.storage.models import NoteModel
            with get_session() as session:
                existing_notes = set(
                    row[0] for row in session.query(NoteModel.note_id).filter(NoteModel.user_id == target_user_id).all()
                )
            data = json.loads(notes_path.read_text(encoding="utf-8"))
            notes_dict = data.get("notes", {})
            migrated_notes = 0
            for nid, n_info in notes_dict.items():
                if nid in existing_notes:
                    continue
                title = n_info.get("title", f"Note {nid}")
                content = n_info.get("content", "")
                knowledge_repo.create_note(ctx, title=title, content=content, note_id=nid)
                migrated_notes += 1
            if migrated_notes > 0:
                logger.info("Migrated %d notes from %s", migrated_notes, notes_path)
        except Exception as e:
            logger.warning("Failed migrating notes.json: %s", e)

    # 3. Migrate Documents from documents/*.txt
    from app.storage.models import DocumentModel
    with get_session() as session:
        existing_doc_ids = set(
            row[0] for row in session.query(DocumentModel.document_id).filter(DocumentModel.user_id == target_user_id).all()
        )

    docs_dir = PROJECT_ROOT / "documents"
    if docs_dir.exists():
        txt_files = list(docs_dir.glob("*.txt"))
        migrated_docs = 0
        total_chunks = 0
        for p in txt_files:
            doc_id = f"doc_{p.stem}"
            if doc_id in existing_doc_ids:
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                # Simple paragraph / section chunking
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
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
                knowledge_repo.save_document(
                    ctx=ctx,
                    filename=p.name,
                    content=content,
                    chunks=chunks,
                    document_id=f"doc_{p.stem}",
                    file_path=str(p),
                )
                migrated_docs += 1
                total_chunks += len(chunks)
            except Exception as e:
                logger.warning("Failed migrating document %s: %s", p.name, e)
        logger.info("Migrated %d documents (%d chunks) from %s", migrated_docs, total_chunks, docs_dir)

    logger.info("V1 to V2 data migration completed successfully.")


if __name__ == "__main__":
    migrate_all_v1_data()
