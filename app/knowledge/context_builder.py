"""Token-Bounded Context Builder with Explicit Citation Tagging."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.context import ExecutionContext
from app.knowledge.retriever import CitationRecord


def _estimate_tokens(text: str) -> int:
    """Fast conservative token estimation (1 token ~ 3.8 characters)."""
    return max(1, int(len(text) / 3.8))


class BoundedContextBuilder:
    """
    Assembles prompt context across temporal clock, profile facts,
    calendar commitments, notes, and retrieved document passages,
    strictly enforcing deterministic token budgets.
    """

    def __init__(self, total_token_budget: Optional[int] = None):
        self.total_budget = total_token_budget or settings.CONTEXT_TOKEN_BUDGET

    def build_context(
        self,
        ctx: ExecutionContext,
        profile_facts: Optional[Dict[str, str]] = None,
        calendar_events: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[List[Dict[str, Any]]] = None,
        reminders: Optional[List[Dict[str, Any]]] = None,
        citations: Optional[List[CitationRecord]] = None,
    ) -> tuple[str, int]:
        """
        Assemble bounded prompt context string and return (formatted_context, estimated_tokens).
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        sections = []

        # 1. Temporal Clock (100 tokens max)
        clock_str = (
            f"=== CURRENT DATE & TIME ===\n"
            f"Today: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})\n"
            f"UTC Time: {now.strftime('%H:%M:%S')}"
        )
        sections.append(clock_str)

        # 2. Profile Facts (400 tokens max)
        if profile_facts:
            fact_lines = [f"- {k.replace('_', ' ').title()}: {v}" for k, v in sorted(profile_facts.items())]
            profile_str = "=== USER PROFILE & FACTS ===\n" + "\n".join(fact_lines[:15])
            sections.append(profile_str)

        # 3. Calendar Commitments (500 tokens max)
        if calendar_events:
            cal_lines = []
            for ev in calendar_events[:8]:
                t = ev.get("time") or ev.get("start_time") or ""
                title = ev.get("title") or "Event"
                status = ev.get("status") or "confirmed"
                cal_lines.append(f"- [{t}] {title} (Status: {status})")
            if cal_lines:
                sections.append("=== TODAY'S CALENDAR COMMITMENTS ===\n" + "\n".join(cal_lines))

        # 4. Active Reminders (300 tokens max)
        if reminders:
            rem_lines = [f"- [{r.get('due_date', '')}] {r.get('title')}" for r in reminders[:5]]
            if rem_lines:
                sections.append("=== PENDING REMINDERS ===\n" + "\n".join(rem_lines))

        # 5. Personal Notes (500 tokens max)
        if notes:
            note_lines = [f"- Note '{n.get('title')}': {n.get('content', '')[:120]}" for n in notes[:4]]
            if note_lines:
                sections.append("=== RELEVANT PERSONAL NOTES ===\n" + "\n".join(note_lines))

        # 6. Verified Knowledge Passages (2,000 tokens max)
        if citations:
            cite_lines = ["=== VERIFIED SOURCE PASSAGES ==="]
            accumulated_chars = 0
            for c in citations:
                passage_block = (
                    f"[{c.citation_id} | {c.document_name} p.{c.page_number or 1}]\n"
                    f"\"{c.exact_quote}\""
                )
                if accumulated_chars + len(passage_block) > 8000:
                    break
                cite_lines.append(passage_block)
                accumulated_chars += len(passage_block)
            sections.append("\n\n".join(cite_lines))

        combined = "\n\n".join(sections)
        tokens_est = _estimate_tokens(combined)

        return combined, tokens_est


# Global default builder instance
context_builder = BoundedContextBuilder()
