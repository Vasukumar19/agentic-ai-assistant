import re

def evaluate_routing(expected_route, actual_route):
    if not expected_route:
        return None
    return expected_route == actual_route

def evaluate_tool_selection(expected_tools, actual_messages):
    """
    Checks if the expected tools were called at least once in the messages.
    Returns (exact_match, precision, recall)
    """
    if expected_tools is None:
        return None
        
    actual_tools = set()
    for msg in actual_messages:
        # Check if it's an AIMessage with tool_calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                actual_tools.add(tc["name"])
    
    expected_set = set(expected_tools)
    
    exact_match = (expected_set == actual_tools)
    precision = len(expected_set.intersection(actual_tools)) / len(actual_tools) if actual_tools else (1.0 if not expected_set else 0.0)
    recall = len(expected_set.intersection(actual_tools)) / len(expected_set) if expected_set else (1.0 if not actual_tools else 0.0)
    
    return {
        "exact_match": exact_match,
        "precision": precision,
        "recall": recall,
        "actual_tools": list(actual_tools)
    }

def evaluate_tool_success(actual_messages):
    """
    Checks ToolMessages for errors. 
    Assumes standard Langchain ToolNode behavior where errors might be captured in the message or 
    the system didn't crash. If the graph finished, we assume tools didn't raise fatal unhandled exceptions,
    but they might contain 'Error:' strings.
    """
    tool_calls = 0
    errors = 0
    for msg in actual_messages:
        if getattr(msg, "type", "") == "tool":
            tool_calls += 1
            if "Error" in str(msg.content) or "Exception" in str(msg.content):
                errors += 1
    
    if tool_calls == 0:
        return None
        
    return {
        "total_calls": tool_calls,
        "errors": errors,
        "success_rate": (tool_calls - errors) / tool_calls
    }

def evaluate_context_coverage(expected_keywords, combined_context):
    if not expected_keywords:
        return None
        
    if not combined_context:
        return 0.0
        
    context_lower = combined_context.lower()
    found = 0
    for kw in expected_keywords:
        if kw.lower() in context_lower:
            found += 1
            
    return found / len(expected_keywords)

def extract_token_usage(messages):
    input_tokens = 0
    output_tokens = 0
    llm_calls = 0
    
    for msg in messages:
        if getattr(msg, "type", "") == "ai":
            llm_calls += 1
            meta = getattr(msg, "response_metadata", {})
            usage = meta.get("token_usage", {})
            if hasattr(usage, "prompt_tokens"):
                input_tokens += getattr(usage, "prompt_tokens", 0)
                output_tokens += getattr(usage, "completion_tokens", 0)
            elif isinstance(usage, dict):
                input_tokens += usage.get("prompt_tokens", 0)
                output_tokens += usage.get("completion_tokens", 0)
            
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "llm_calls": llm_calls
    }

def calculate_cost(model_name, input_tokens, output_tokens):
    # Dummy pricing fallback or known pricing
    pricing = {
        "llama-3.1-70b-versatile": {"input": 0.59 / 1e6, "output": 0.79 / 1e6},
        "llama3-70b-8192": {"input": 0.59 / 1e6, "output": 0.79 / 1e6},
        "qwen/qwen3.6-27b": {"input": 0.30 / 1e6, "output": 0.30 / 1e6}, # example
        "openai/gpt-oss-120b": {"input": 0.50 / 1e6, "output": 0.50 / 1e6} # example
    }
    
    if model_name in pricing:
        return (input_tokens * pricing[model_name]["input"]) + (output_tokens * pricing[model_name]["output"])
    
    return None
