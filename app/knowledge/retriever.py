"""Hybrid Knowledge Retriever with Verified Citation Provenance."""

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.context import ExecutionContext
from app.knowledge.repository import knowledge_repo

logger = logging.getLogger(__name__)


class CitationRecord(BaseModel):
    """Verifiable source passage citation record."""
    citation_id: str                    # Unique tag in prompt: "cite_01"
    document_id: str                    # Document ID
    document_name: str                  # Human-readable filename
    chunk_id: str                       # Exact chunk identifier
    page_number: Optional[int] = None   # Source page
    relevance_score: float              # Cross-Encoder or cosine relevance score
    exact_quote: str                    # Passage text excerpt


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class HybridKnowledgeRetriever:
    """
    Retrieves relevant passages across documents, notes, and facts
    and attaches verified citation provenance.
    """

    def __init__(self):
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                from app.core.config import settings
                self._embedder = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
            except Exception as e:
                logger.warning("Embedder could not be loaded: %s", e)
        return self._embedder

    def retrieve(
        self,
        ctx: ExecutionContext,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.2,
    ) -> List[CitationRecord]:
        """
        Execute hybrid retrieval across ingested document chunks for this tenant.
        Returns top-k passages with explicit CitationRecord metadata.
        """
        chunks = knowledge_repo.get_all_chunks(ctx)
        if not chunks:
            return []

        embedder = self._get_embedder()
        q_vec = None
        if embedder:
            try:
                q_vec = embedder.encode(query).tolist()
            except Exception:
                q_vec = None

        scored_candidates: List[tuple[float, Dict[str, Any]]] = []

        import re
        STOPWORDS = {"what", "is", "the", "to", "of", "for", "in", "according", "a", "an", "do", "how", "on", "at", "by", "with", "from", "my", "me", "are", "per"}
        q_raw_tokens = re.findall(r"\w+", query.lower())
        q_terms = [t for t in q_raw_tokens if t not in STOPWORDS] or q_raw_tokens

        for c in chunks:
            content = c["content"]
            c_text_lower = content.lower()

            # 1. Lexical keyword overlap score
            term_matches = sum(1 for t in q_terms if t in c_text_lower or (len(t) > 4 and t[:4] in c_text_lower))
            lexical_score = term_matches / max(len(q_terms), 1)

            # 2. Dense vector cosine score
            emb = c.get("embedding")
            if (not emb) and embedder:
                try:
                    emb = embedder.encode(content).tolist()
                    c["embedding"] = emb
                except Exception:
                    emb = None

            vector_score = 0.0
            if q_vec and emb:
                vector_score = _cosine_similarity(q_vec, emb)
                combined_score = 0.70 * vector_score + 0.30 * lexical_score
            else:
                combined_score = lexical_score

            if combined_score >= score_threshold:
                scored_candidates.append((combined_score, c))

        # Sort descending by relevance score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[:top_k]

        citations: List[CitationRecord] = []
        for idx, (score, chunk) in enumerate(top_candidates, 1):
            quote = chunk["content"].strip()
            if len(quote) > 500:
                quote = quote[:500] + "..."
            citations.append(
                CitationRecord(
                    citation_id=f"cite_{idx:02d}",
                    document_id=chunk["document_id"],
                    document_name=chunk["filename"],
                    chunk_id=chunk["chunk_id"],
                    page_number=chunk.get("page_number", 1),
                    relevance_score=round(score, 4),
                    exact_quote=quote,
                )
            )

        return citations


def validate_citation_provenance(ctx: ExecutionContext, citation: CitationRecord) -> Tuple[bool, Optional[str]]:
    """
    Validate that a CitationRecord has verifiable provenance:
      - Belongs to the authenticated tenant
      - References an existing Document and DocumentChunk
      - Has matching document metadata and excerpt content
    """
    from app.storage.database import get_session
    from app.storage.models import DocumentModel, DocumentChunkModel

    with get_session() as session:
        chunk = (
            session.query(DocumentChunkModel)
            .filter_by(chunk_id=citation.chunk_id, user_id=ctx.user_id)
            .first()
        )
        if not chunk:
            return False, f"Chunk '{citation.chunk_id}' does not exist or belongs to another tenant."

        doc = (
            session.query(DocumentModel)
            .filter_by(document_id=citation.document_id, user_id=ctx.user_id)
            .first()
        )
        if not doc:
            return False, f"Document '{citation.document_id}' does not exist or belongs to another tenant."

        if doc.filename != citation.document_name:
            return False, f"Document name mismatch: expected '{doc.filename}', got '{citation.document_name}'."

        # Verify quote matches source content
        cleaned_quote = citation.exact_quote.rstrip(".")
        if cleaned_quote not in chunk.content and chunk.content[:len(cleaned_quote)] != cleaned_quote:
            return False, "Citation exact_quote does not match source chunk content."

        return True, None


# Global retriever instance
knowledge_retriever = HybridKnowledgeRetriever()
