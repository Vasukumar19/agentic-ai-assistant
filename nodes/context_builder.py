"""
Context Builder Node
====================

Merges retrieved contexts (profile, semantic, RAG) into a single prompt context
for the LLM agent.

This is where we assemble all the information that the agent will reason over.
"""


def context_builder_node(state: dict) -> dict:
    """
    Build combined context from all retrieval sources.
    
    This context will be injected into the agent prompt.
    
    Args:
        state: AgentState with context fields (profile_context, semantic_context, rag_context)
    
    Returns:
        Updated state (no combined_context field - used in messages instead)
    """
    profile_context = state.get("profile_context", "")
    semantic_context = state.get("semantic_context", "")
    rag_context = state.get("rag_context", "")
    
    # Build context sections
    context_parts = []
    
    if profile_context:
        context_parts.append(profile_context)
    
    if semantic_context:
        context_parts.append(semantic_context)
    
    if rag_context:
        context_parts.append(rag_context)
    
    combined = "\n\n".join(context_parts) if context_parts else ""
    
    if combined:
        print(f"  [Context Builder] Built context from {len(context_parts)} sources ({len(combined)} chars)")
    else:
        print(f"  [Context Builder] No context to build")
    
    # Store combined context in state for agent node to access
    return {"_combined_context": combined}
