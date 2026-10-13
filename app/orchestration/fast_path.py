"""Fast-Path Execution Loop: Single-turn retrieval & synthesis (<1,500ms)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.context import ExecutionContext
from app.knowledge.repository import knowledge_repo
from app.knowledge.retriever import knowledge_retriever, CitationRecord
from app.knowledge.context_builder import context_builder
from app.observability.sink import emit_event

logger = logging.getLogger(__name__)


def _extract_memory_pairs(text: str) -> List[tuple[str, str]]:
    """Rule-based extractor for common profile fact utterances."""
    pairs = []
    t_lower = text.lower()

    # Job / Role
    m = re.search(r"(?:my (?:current )?(?:job )?(?:title|role) is|i work as an?)\s+([^,\.]+)", t_lower)
    if m:
        pairs.append(("role", m.group(1).strip().title()))

    # Location
    m = re.search(r"(?:my (?:new )?home location is|i live in|i moved to)\s+([^,\.]+)", t_lower)
    if m:
        pairs.append(("location", m.group(1).strip().title()))

    # Primary Language
    m = re.search(r"(?:my (?:native|primary) language is)\s+([^,\.]+)", t_lower)
    if m:
        pairs.append(("primary_language", m.group(1).strip().title()))

    # Primary Editor / Tool
    m_ed = re.search(r"i work with\s+([a-zA-Z0-9\s]+?)\s+as my primary editor", t_lower)
    if m_ed:
        pairs.append(("primary_editor", m_ed.group(1).strip().title()))
    else:
        m_ed2 = re.search(r"(?:my primary editor is)\s+([^,\.]+)", t_lower)
        if m_ed2:
            pairs.append(("primary_editor", m_ed2.group(1).strip().title()))

    # Name
    m = re.search(r"(?:my name is|call me)\s+([^,\.]+)", t_lower)
    if m:
        pairs.append(("name", m.group(1).strip().title()))

    return pairs


class FastPathExecutor:
    """Executes single-turn conversational turns and direct knowledge lookups."""

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from llm import get_llm
            self._llm = get_llm()
        return self._llm

    def execute(self, ctx: ExecutionContext, query: str, route: str) -> Dict[str, Any]:
        """Execute fast path."""
        # 1. Casual Chat
        if route == "FAST_CHAT":
            emit_event(ctx, "fast_path", "CHAT_RESPONSE")
            return {
                "answer": "Hello! I am your Personal Knowledge & Planning Assistant. How can I help you today?",
                "execution_status": "completed",
                "citations": [],
            }

        # 2. Personal Memory Mutation
        if route == "MEMORY_MUTATION":
            pairs = _extract_memory_pairs(query)
            if not pairs:
                pairs = [("general_preference", query.replace("Remember that", "").strip())]

            saved_keys = []
            for k, v in pairs:
                knowledge_repo.set_profile_fact(ctx, key=k, value=v)
                saved_keys.append(f"{k} = {v}")

            extracted = {k: v for k, v in pairs}
            emit_event(ctx, "fast_path", "MEMORY_SAVED", payload={"saved": saved_keys})
            return {
                "answer": f"I have saved that to your personal profile: {', '.join(saved_keys)}.",
                "execution_status": "completed",
                "citations": [],
                "extracted_profile": extracted,
                "route": "memory_update",
            }

        # 3. Fast Information Retrieval & Synthesis
        profile_facts = knowledge_repo.get_profile_facts(ctx)
        citations = knowledge_retriever.retrieve(ctx, query=query, top_k=4)

        context_str, token_est = context_builder.build_context(
            ctx=ctx,
            profile_facts=profile_facts,
            citations=citations,
        )

        llm = self._get_llm()
        prompt = f"""You are a precise Personal Knowledge Assistant.
Answer the user's question accurately using ONLY the context provided below.
If citing information from verified source passages, use the passage tag (e.g. [cite_01]) directly in your text.
If the answer is not in the context, state clearly that you do not have that information.

{context_str}

User Question: {query}
Answer:"""

        emit_event(ctx, "fast_path", "SYNTHESIS_STARTED", payload={"tokens_est": token_est, "citations": len(citations)})
        try:
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=prompt)])
            answer_text = response.content
        except Exception as e:
            logger.error("Fast path LLM failure: %s", e)
            answer_text = f"I retrieved the relevant information but encountered an error synthesizing the answer: {e}"

        profile_ctx_str = "\n".join([f"{k}: {v}" for k, v in profile_facts.items()])

        emit_event(ctx, "fast_path", "SYNTHESIS_COMPLETED")
        return {
            "answer": answer_text,
            "citations": [c.model_dump() for c in citations],
            "execution_status": "completed",
            "rag_context": context_str,
            "retrieved_chunks": [c.model_dump() for c in citations],
            "profile_context": profile_ctx_str,
        }


# Global default fast-path executor
fast_path = FastPathExecutor()
