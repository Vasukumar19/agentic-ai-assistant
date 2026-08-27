"""
Deterministic Generic Goal Fulfillment Guard
============================================

Generic capability-level goal tracking and fulfillment verification.
Enforces that multi-operation user requests are not terminated prematurely.

Strict Constraints:
- ZERO service-specific keyword routing (e.g. no "meeting"->calendar or "reminder"->reminders).
- Operates on abstract operational categories (read, calculate, create, list, update, delete).
- Pure verification: answers 'Is it safe to allow FINAL?' without deciding which tool must run.
"""

import re
from typing import Tuple, List, Dict, Any


# Abstract operation definitions and generic action synonyms
OPERATION_PATTERNS = [
    ("calculate", re.compile(r"\b(calculate|compute|math|multiply|divide|add up|sum|percentage|% of|double the)\b", re.IGNORECASE)),
    ("create", re.compile(r"\b(create|make|save|write|set up|set a|schedule|book|new)\b", re.IGNORECASE)),
    ("update", re.compile(r"\b(update|modify|edit|complete|mark|append|change)\b", re.IGNORECASE)),
    ("delete", re.compile(r"\b(delete|remove|cancel|clear|wipe)\b", re.IGNORECASE)),
    ("read", re.compile(r"\b(read|get|fetch|details of|show me note|show me event)\b", re.IGNORECASE)),
    ("list", re.compile(r"\b(list|search|find|show my|show all|filter|how many)\b", re.IGNORECASE)),
]

# Tool -> Abstract Operation mapping
TOOL_OPERATION_MAP = {
    # Calculate
    "calculator": "calculate",
    "math": "calculate",
    
    # Read
    "filesystem.read_file": "read",
    "notes.read": "read",
    "calendar.get_event": "read",
    "reminders.get": "read",
    
    # Create
    "calendar.create_event": "create",
    "notes.create": "create",
    "reminders.create": "create",
    "filesystem.write_file": "create",
    
    # List / Search
    "calendar.list_events": "list",
    "notes.list": "list",
    "reminders.list": "list",
    "filesystem.list_directory": "list",
    "web_search": "list",
    
    # Update
    "calendar.update_event": "update",
    "notes.append": "update",
    "reminders.complete": "update",
    
    # Delete
    "calendar.delete_event": "delete",
    "notes.delete": "delete",
    "reminders.delete": "delete",
}


def extract_abstract_operations(query: str) -> List[str]:
    """
    Extract abstract capability operations from a query in textual appearance order.
    Does NOT infer or hardcode specific services.
    """
    if not query:
        return []
        
    found_ops = []
    # Identify positions of matches to preserve ordering
    matches = []
    for op_name, pattern in OPERATION_PATTERNS:
        for m in pattern.finditer(query):
            matches.append((m.start(), op_name))
            
    # Sort matches by appearance in text
    matches.sort(key=lambda x: x[0])
    
    # Collect unique operations in order of appearance
    seen = set()
    for _, op in matches:
        if op not in seen:
            seen.add(op)
            found_ops.append(op)
            
    return found_ops if found_ops else ["read"]


def map_tool_to_operation(tool_name: str) -> str:
    """Map a tool name to its abstract capability category."""
    if not tool_name:
        return "unknown"
    t = tool_name.lower()
    for tool_key, op in TOOL_OPERATION_MAP.items():
        if tool_key == t or tool_key in t or tool_key.replace(".", "_") in t:
            return op
        # check suffix (e.g. read_file, get_event)
        suffix = tool_key.split(".")[-1]
        if suffix in t:
            return op
    return "unknown"


def goal_fulfillment_check(
    state: Dict[str, Any],
    query: str,
    tool_results: List[Dict[str, Any]]
) -> Tuple[str, List[str], List[str], List[str]]:
    """
    Evaluates whether the agent has completed all required operations for the goal.
    
    Returns:
        (status, required_operations, completed_operations, remaining_operations)
        
    status values:
        - "FULFILLED": All required operations completed, or only single operation required.
        - "INCOMPLETE": Required operations remain, safe to continue execution.
        - "BLOCKED": Critical failure prevents further progress.
    """
    required = extract_abstract_operations(query)
    
    # Identify completed operations from successful tool results
    completed = []
    has_blocking_error = False
    
    for r in tool_results:
        tool = r.get("tool", "")
        res_str = str(r.get("result", ""))
        is_error = res_str.lower().startswith("error") or r.get("error")
        
        op = map_tool_to_operation(tool)
        if not is_error and op != "unknown":
            if op not in completed:
                completed.append(op)
        elif is_error:
            # Check if this error represents an unrecoverable blocker
            if "not found" in res_str.lower() and len(tool_results) >= 2:
                has_blocking_error = True
                
    # Calculate remaining operations preserving required order
    remaining = [op for op in required if op not in completed]
    
    # If no remaining operations or only 1 generic operation asked, fulfilled
    if not remaining:
        return "FULFILLED", required, completed, []
        
    # If there are remaining operations but required was just 1 operation and tool was called
    if len(required) <= 1 and completed:
        return "FULFILLED", required, completed, []
        
    if has_blocking_error and len(tool_results) >= 4:
        return "BLOCKED", required, completed, remaining
        
    return "INCOMPLETE", required, completed, remaining
