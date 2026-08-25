"""
Context Builder Node
====================

Merges retrieved contexts (profile, semantic, RAG) into a single prompt context
for the LLM agent.

This is where we assemble all the information that the agent will reason over.
"""

import logging

logger = logging.getLogger(__name__)


def context_builder_node(state: dict) -> dict:
    """
    Build combined context from all retrieval sources.
    """
    import time
    t0 = time.perf_counter()
    profile_context = state.get("profile_context", "")
    semantic_context = state.get("semantic_context", "")
    rag_context = state.get("rag_context", "")

    context_parts = []
    if profile_context:
        context_parts.append(profile_context)
    if semantic_context:
        context_parts.append(semantic_context)
    if rag_context:
        context_parts.append(rag_context)
    combined = "\n\n".join(context_parts) if context_parts else ""

    if combined:
        logger.info("Built context from %d source(s) (%d chars)", len(context_parts), len(combined))
    else:
        logger.debug("No context to build")

    dur = int((time.perf_counter() - t0) * 1000)
    try:
        from observability.trace import make_event, append_event, add_latency
        add_latency(state, "context_builder", dur)
        ev = make_event(state, "CONTEXT_BUILD", "context_builder", duration_ms=dur, status="success",
                        metadata={"sources": len(context_parts), "combined_chars": len(combined),
                                  "has_profile": bool(profile_context), "has_semantic": bool(semantic_context),
                                  "has_rag": bool(rag_context)})
        append_event(state, ev)
    except Exception:
        pass
    return {"_combined_context": combined, "trace_events": state.get("trace_events"),
            "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown")}