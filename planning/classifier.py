"""Generic task-complexity classification — no service-specific rules.

Signals used (all derived from registry tool metadata + linguistic structure):
- how many known tools the goal explicitly references
- chaining / sequencing signals ("then", "after that", "and use its result")
- dependency signals (output of one op feeding another)
- multi-action coordination
"""

from __future__ import annotations

import re
from typing import Iterable

CLASSES = ("SIMPLE", "DEPENDENT", "MULTI_STEP", "UNCERTAIN")

_CHAIN_SIGNALS = [
    " and then", " then ", " after that", " afterwards", " once that",
    "followed by", "next,", " next ",
]
_DEP_SIGNALS = [
    "use the result", "using the result", "based on the result", "from the result",
    "its result", "their results", "the returned", "returned value", "that value",
    "using it", "from it ", "of it ", "with the output", "the output of",
    "the result", "result to", "into a", "from that",
]
_MULTI_ACTION = [
    "create", "add", "save", "write", "list", "read", "get", "remind", "schedule",
]


def classify_complexity(goal: str, valid_tool_names: Iterable[str]) -> str:
    """Return one of SIMPLE/DEPENDENT/MULTI_STEP/UNCERTAIN. Generic over tool names."""
    low = f" {goal.lower().strip()} "
    # normalize alias mentions: count distinct known tools referenced
    referenced = set()
    for name in valid_tool_names:
        base = name.replace(".", "_").lower()
        if base in low.replace(" ", "_") or name.lower() in low:
            referenced.add(name)
        else:
            # match server.tool or server_tool token with word-ish boundaries
            tok = re.escape(name.lower())
            if re.search(rf"(?<![a-z0-9]){tok}(?![a-z0-9])", low.replace("_", ".") ) or \
               re.search(rf"(?<![a-z0-9.]){tok}(?![a-z0-9.])", low):
                referenced.add(name)
    n_tools = len(referenced)

    has_chain = any(s in low for s in _CHAIN_SIGNALS)
    has_dep = any(s in low for s in _DEP_SIGNALS)
    action_count = sum(1 for a in _MULTI_ACTION if a in low)

    if n_tools >= 3 or (n_tools >= 2 and has_chain and (has_dep or action_count >= 2)):
        return "MULTI_STEP"
    if n_tools >= 2 or (n_tools == 1 and has_dep) or (has_chain and action_count >= 2):
        return "DEPENDENT"
    if n_tools == 1:
        return "SIMPLE"
    if action_count >= 2 or has_chain:
        return "UNCERTAIN"
    return "SIMPLE"
