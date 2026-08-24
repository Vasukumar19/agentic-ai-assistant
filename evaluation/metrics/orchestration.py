"""
Phase 3: Multi-Step Tool Orchestration Metrics
"""

def evaluate_tool_selection_accuracy(expected: list[str], actual: list[str]) -> bool:
    """Exact match of the set of tools used vs expected."""
    return set(expected) == set(actual)

def evaluate_tool_sequence_accuracy(expected: list[str], actual: list[str]) -> bool:
    """Exact match of the ordered list of tools used vs expected."""
    return expected == actual

def evaluate_multi_step_completion(expected: list[str], actual: list[str]) -> bool:
    """% of queries requiring >1 tool where the full sequence was completed."""
    if len(expected) <= 1:
        return True # N/A, but we can treat as true if it didn't fail
    return expected == actual

def evaluate_unnecessary_tool(expected: list[str], actual: list[str]) -> bool:
    """True if an unexpected tool was called."""
    return bool(set(actual) - set(expected))

def evaluate_missing_tool(expected: list[str], actual: list[str]) -> bool:
    """True if a required tool was NOT called."""
    return bool(set(expected) - set(actual))

def evaluate_premature_termination(expected: list[str], actual: list[str]) -> bool:
    """True if the agent stopped before completing the sequence."""
    if len(actual) < len(expected):
        return actual == expected[:len(actual)]
    return False

def categorize_failure(expected: list[str], actual: list[str]) -> str | None:
    """Categorizes the failure mode based on expected and actual sequences."""
    if expected == actual:
        return None
        
    if not actual:
        return "missing_tool"
    elif evaluate_premature_termination(expected, actual):
        return "premature_stop"
    elif evaluate_unnecessary_tool(expected, actual):
        return "unnecessary_tool"
    elif evaluate_missing_tool(expected, actual):
        return "missing_tool"
    elif set(actual) == set(expected) and actual != expected:
        return "wrong_order"
    else:
        return "wrong_tool"
