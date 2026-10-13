"""Interactive & One-Shot CLI Interface for Personal Knowledge & Planning Assistant."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from app.assistant import assistant_app
from app.core.config import settings
from app.knowledge.repository import knowledge_repo
from app.core.context import ExecutionContext


def print_banner():
    banner = """
========================================================================
         PERSONAL KNOWLEDGE & PLANNING ASSISTANT (V2 MONOLITH)
========================================================================
 Dual-Path Orchestration • Tool Gateway • Bounded Context • Provable Safety
 LLM: Ollama (qwen3:8b)   | Storage: SQLite (WAL)   | Tenancy: Isolated
========================================================================
Type your request, or commands: /today, /knowledge, /reminders, /help, /exit
"""
    print(banner)


def handle_today(user_id: str):
    """Shortcut command for today's briefing."""
    print("\n[Gathering Today's Briefing & Schedule...]\n")
    query = "Give me a comprehensive daily briefing for today with what I have scheduled and how I should prepare."
    t0 = time.perf_counter()
    res = assistant_app.invoke(query=query, user_id=user_id)
    lat_ms = (time.perf_counter() - t0) * 1000
    print(f"Assistant ({lat_ms:.0f}ms | route: {res.get('route')}):")
    print(res.get("answer", ""))


def handle_knowledge(user_id: str):
    """Shortcut command for viewing stored knowledge."""
    ctx = ExecutionContext.create(user_id=user_id)
    facts = knowledge_repo.get_profile_facts(ctx)
    notes = knowledge_repo.list_notes(ctx)
    print("\n=== My Profile Facts ===")
    if not facts:
        print("  (No facts saved yet)")
    else:
        for k, v in facts.items():
            print(f"  • {k}: {v}")

    print("\n=== Saved Notes ===")
    if not notes:
        print("  (No notes found)")
    else:
        for n in notes:
            print(f"  • [{n['note_id']}] {n['title']}: {n['content'][:60]}...")
    print()


def handle_reminders(user_id: str):
    """Shortcut command for viewing reminders."""
    ctx = ExecutionContext.create(user_id=user_id)
    rems = knowledge_repo.list_reminders(ctx)
    print("\n=== Active Reminders ===")
    if not rems:
        print("  (No reminders found)")
    else:
        for r in rems:
            print(f"  • [{r['status']}] {r['title']} (Due: {r['due_date']})")
    print()


def run_interactive(user_id: str = "usr_default"):
    """Run interactive terminal session."""
    print_banner()
    pending_token: Optional[str] = None
    pending_action: Optional[str] = None

    while True:
        try:
            prompt_str = f"[{user_id}] > "
            user_input = input(prompt_str).strip()
            if not user_input:
                continue

            if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                print("\nGoodbye!\n")
                break

            if user_input.lower() == "/help":
                print("\nAvailable Commands:")
                print("  /today      - View daily briefing and calendar commitments")
                print("  /knowledge  - Inspect profile facts and personal notes")
                print("  /reminders  - View pending and completed reminders")
                print("  /exit       - Exit application\n")
                continue

            if user_input.lower() == "/today":
                handle_today(user_id)
                continue

            if user_input.lower() == "/knowledge":
                handle_knowledge(user_id)
                continue

            if user_input.lower() == "/reminders":
                handle_reminders(user_id)
                continue

            # Check if answering a pending approval
            token_to_pass = None
            if pending_token:
                if user_input.lower() in ("yes", "y", "confirm", "approve"):
                    token_to_pass = pending_token
                    user_input = f"Execute approved action: {pending_action}"
                    pending_token = None
                    pending_action = None
                elif user_input.lower() in ("no", "n", "cancel", "deny"):
                    print("[Action Cancelled by User]\n")
                    pending_token = None
                    pending_action = None
                    continue
                else:
                    # User asked something else, discard pending approval
                    pending_token = None
                    pending_action = None

            t0 = time.perf_counter()
            res = assistant_app.invoke(
                query=user_input,
                user_id=user_id,
                approval_token=token_to_pass,
            )
            lat_ms = (time.perf_counter() - t0) * 1000

            status = res.get("execution_status")
            print(f"\nAssistant ({lat_ms:.0f}ms | route: {res.get('route')}):")
            print(res.get("answer", ""))

            # Handle citations display
            citations = res.get("citations") or []
            if citations:
                print("\nSources Cited:")
                for c in citations:
                    print(f"  • [{c.get('citation_id')}] {c.get('document_name')} ({c.get('chunk_id')}, score: {c.get('relevance_score', 0):.2f})")

            # Handle approval gate pause
            if status == "awaiting_approval":
                approval_info = res.get("pending_approval") or {}
                pending_token = approval_info.get("approval_token")
                pending_action = approval_info.get("tool_name")
                print(f"\n[APPROVAL REQUIRED]")
                print(f"  Tool: {pending_action}")
                print(f"  Arguments: {approval_info.get('arguments')}")
                print(f"  Token: {pending_token}")
                print(f"Type 'yes' to approve and execute, or 'no' to abort.\n")

            print()

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break
        except Exception as e:
            print(f"\n[Error] {e}\n")


def run_one_shot(query: str, user_id: str = "usr_default"):
    """Execute single query and display output."""
    t0 = time.perf_counter()
    res = assistant_app.invoke(query=query, user_id=user_id)
    lat_ms = (time.perf_counter() - t0) * 1000

    print(res.get("answer", ""))
    citations = res.get("citations") or []
    if citations:
        print("\nSources:")
        for c in citations:
            print(f"  - [{c.get('citation_id')}] {c.get('document_name')}")


def main():
    parser = argparse.ArgumentParser(description="Personal Knowledge & Planning Assistant CLI")
    parser.add_argument("query", nargs="*", help="Optional one-shot query to execute")
    parser.add_argument("--user", default="usr_default", help="Tenant User ID")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive session")

    args = parser.parse_args()

    if args.query:
        query_text = " ".join(args.query)
        run_one_shot(query=query_text, user_id=args.user)
    else:
        run_interactive(user_id=args.user)


if __name__ == "__main__":
    main()
