"""Typed Intent Classifier for Dual-Path Routing."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.context import ExecutionContext
from app.gateway.manifest import ApprovalRequirement, SideEffectLevel

logger = logging.getLogger(__name__)

# Basic greeting keywords
GREETINGS = {
    "hi", "hello", "hey", "good morning", "good evening", "good night",
    "howdy", "sup", "greetings", "thanks", "thank you", "bye", "goodbye"
}

# Verbs signaling deliberate side-effect actions
ACTION_VERBS = [
    "delete", "remove", "create", "make", "schedule", "calculate", "compute",
    "update", "modify", "complete", "fetch url", "post", "drop", "wipe"
]

# Personal memory cue phrases
MEMORY_CUES = [
    "remember that", "remember my", "my name is", "my role is", "my job is",
    "i live in", "i prefer", "my favorite", "my primary language is",
    "actually my", "actually, i", "change my", "i do not eat", "i dont eat", "i used to",
    "moved to", "recently moved", "home location", "i work with", "primary editor", "native language",
    "my team was", "team is"
]


class IntentRoute(str):
    FAST_CHAT = "FAST_CHAT"
    MEMORY_MUTATION = "MEMORY_MUTATION"
    FAST_INFO = "FAST_INFO"
    DELIBERATE = "DELIBERATE"


class IntentClassification(BaseModel):
    """Output of Intent Classification."""
    route: str  # FAST_CHAT | MEMORY_MUTATION | FAST_INFO | DELIBERATE
    confidence: float = 1.0
    extracted_memory_fact: Optional[Dict[str, str]] = None
    target_domains: List[str] = Field(default_factory=list)
    requires_approval: bool = False


class IntentRouter:
    """Classifies user intent into Fast-Path or Deliberate-Path."""

    def classify(self, ctx: ExecutionContext, query: str) -> IntentClassification:
        clean_q = query.strip()
        q_lower = clean_q.lower()

        if not clean_q:
            return IntentClassification(route=IntentRoute.FAST_CHAT, confidence=1.0)

        # 1. Check for pure greetings / pleasantries
        is_greeting = any(
            q_lower == g
            or q_lower.startswith(f"{g} ")
            or q_lower.startswith(f"{g}!")
            or q_lower.startswith(f"{g},")
            or q_lower.startswith(f"{g}?")
            for g in GREETINGS
        )
        if is_greeting and not any(v in q_lower for v in ["delete", "calculate", "policy", "hotel", "cap"]):
            return IntentClassification(route=IntentRoute.FAST_CHAT, confidence=1.0)

        # 2. Check for personal memory updates / bio facts
        is_mem = any(cue in q_lower for cue in MEMORY_CUES)
        if is_mem:
            # Check if it also requests deliberate action (e.g. "Remember X and delete Y")
            has_action = any(v in q_lower for v in ["delete", "remove", "drop"])
            if not has_action:
                return IntentClassification(
                    route=IntentRoute.MEMORY_MUTATION,
                    confidence=0.95,
                    target_domains=["profile"],
                )

        # 3. Check for deliberate multi-step actions or mutations
        has_destructive = any(v in q_lower for v in ["delete", "remove", "cancel", "drop", "wipe"])
        has_action = any(v in q_lower for v in ACTION_VERBS)
        has_math = bool(re.search(r"\b\d+\s*[\+\-\*\/]\s*\d+\b", q_lower)) or "calculate" in q_lower or "compute" in q_lower
        clean_q_tools = q_lower.replace("calendar year", "")
        has_tools = any(w in clean_q_tools for w in [
            "calendar", "meeting", "schedule", "briefing", "timeline", "evt_", "checklist",
            "reminder", "reminders", "fetch", "http://", "https://", "read file", "filesystem",
            "sqlite", "select", "drop table"
        ])

        if has_destructive or has_action or has_math or has_tools:
            return IntentClassification(
                route=IntentRoute.DELIBERATE,
                confidence=0.9,
                requires_approval=has_destructive,
                target_domains=["tools"],
            )

        # 4. Default to Fast-Path Knowledge / Schedule / Profile lookup
        domains = []
        if any(w in q_lower for w in ["calendar", "meeting", "event", "schedule", "free"]):
            domains.append("calendar")
        if any(w in q_lower for w in ["policy", "flight", "hotel", "laptop", "pto", "vacation", "stipend"]):
            domains.append("documents")
        if any(w in q_lower for w in ["my role", "my name", "my preference", "where do i live", "my job"]):
            domains.append("profile")
        if not domains:
            domains = ["documents", "profile"]

        return IntentClassification(
            route=IntentRoute.FAST_INFO,
            confidence=0.85,
            target_domains=domains,
        )


# Global router instance
router = IntentRouter()
