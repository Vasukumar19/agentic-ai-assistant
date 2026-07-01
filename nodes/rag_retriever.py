"""
RAG Retriever Node
==================

Searches through company documents (PDF/TXT) using FAISS semantic search.
Formats results for LLM consumption.
"""

from pathlib import Path
from langchain_community.vectorstores import FAISS
from config import FAISS_INDEX_DIR
from .embeddings import embeddings


def rag_retriever_node(state: dict) -> dict:
    """
    Retrieve relevant documents from FAISS index.
    
    Args:
        state: AgentState with 'retrieval_plan' and 'question' fields
    
    Returns:
        Updated state with 'rag_context' field
    """
    retrieval_plan = state.get("retrieval_plan", {})
    question = state.get("question", "")
    
    rag_context = ""
    
    if not retrieval_plan.get("rag", False):
        return {"rag_context": ""}
    
    try:
        if not FAISS_INDEX_DIR.exists():
            print(f"  [RAG Retriever] No documents found (faiss_index not built)")
            return {"rag_context": ""}
        
        # Load vectorstore
        vectorstore = FAISS.load_local(
            str(FAISS_INDEX_DIR),
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        # Search for relevant documents
        results = vectorstore.similarity_search(question, k=3)
        
        if not results:
            print(f"  [RAG Retriever] No relevant documents found")
            return {"rag_context": ""}
        
        # Format results
        lines = ["=== COMPANY DOCUMENTS ==="]
        
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "")
            
            # Format document reference
            label = f"[Doc {i} | {Path(source).name}"
            if page != "":
                label += f" p.{page + 1}]"
            else:
                label += "]"
            
            lines.append(f"{label}")
            lines.append(doc.page_content.strip())
            lines.append("")  # Blank line between documents
        
        rag_context = "\n".join(lines)
        print(f"  [RAG Retriever] Fetched {len(results)} documents")
        
    except Exception as e:
        print(f"  [RAG Retriever] Error: {e}")
    
    return {"rag_context": rag_context}
