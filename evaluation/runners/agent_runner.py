import time
import sys
import os
# Add root to sys.path so we can import from project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from graph import create_runnable_graph

# We compile the graph once
graph = create_runnable_graph()

def run_agent(query):
    start_time = time.time()
    
    initial_state = {
        "question": query,
        "route": "",
        "retrieval_plan": {"profile": False, "semantic": False, "rag": False},
        "profile_context": "",
        "semantic_context": "",
        "rag_context": "",
        "extracted_profile": {},
        "extracted_semantic": [],
        "answer": "",
        "_combined_context": "",
        "messages": [],
    }
    
    try:
        final_state = graph.invoke(initial_state)
        error = None
        category = None
    except Exception as e:
        final_state = initial_state
        error = str(e)
        category = "exception"
        
    latency = time.time() - start_time
    
    return final_state, latency, error, category
