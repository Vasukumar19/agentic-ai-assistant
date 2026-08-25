"""
LangGraph State Definition
==========================

Defines the state schema for the entire agent workflow.

Key decisions:
- No combined_context (derived dynamically)
- retrieval_plan dict (scalable to future retrievers)
- Supports chat, memory_update, research_query routes
"""

from typing import TypedDict, Annotated, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Unified state for all agent workflows.
    
    Fields:
        question: User's input question/message
        route: "chat" | "memory_update" | "research_query" - determines execution path
        
        retrieval_plan: Dict indicating what to retrieve
            {
                "profile": bool,      # Fetch profile memory
                "semantic": bool,     # Fetch semantic memory
                "rag": bool          # Fetch RAG documents
            }
        
        profile_context: Formatted user profile info (from profile_memory.json)
        semantic_context: Search results from semantic memory (FAISS)
        rag_context: Search results from document FAISS index
        
        extracted_profile: Memory data to save to profile_memory.json
        extracted_semantic: List of memory texts to save to semantic memory
        
        answer: Final response to user
        messages: LangChain message history with add_messages reducer
    """
    
    question: str
    route: str
    
    # Retrieval planning
    retrieval_plan: Optional[dict]
    
    # Retrieved contexts
    profile_context: str
    semantic_context: str
    rag_context: str
    
    # Memory extraction (for memory_update route)
    extracted_profile: dict
    extracted_semantic: list
    
    # Final answer
    answer: str
    
    # Combined context for reasoning
    _combined_context: str
    
    # Retrieval Ground Truth and Metrics
    retrieved_chunks: list
    retrieval_metrics: dict
    
    # Message history
    messages: Annotated[list, add_messages]
    
    # Execution State for Orchestration
    current_step: str
    completed_steps: list[str]
    tool_results: list[dict]
    execution_status: str
    tool_call_count: int
    max_steps: int
    last_action: Optional[str]
    tool_loop_detected: Optional[bool]
    execution_trace: Optional[list[dict]]
