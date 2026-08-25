"""One-shot: recover legacy ReAct agent_node verbatim from git into an
evaluation-only module with minimal import shims."""

import subprocess

src = subprocess.run(
    ["git", "cat-file", "-p", "58687ca^:nodes/agent.py"],
    capture_output=True, text=True, encoding="utf-8", check=True).stdout

header = '''"""
RECOVERED legacy ReAct agent_node (verbatim from git 58687ca^:nodes/agent.py).
Evaluation-only module for the same-model ReAct vs Planner comparison.
Only import shims were adapted: relative -> absolute imports; the Groq
exception import is optional-safe (GroqBadRequestError stays None without
the groq package installed).
"""
'''

end = src.index('"""', src.index('"""') + 3) + 3
body = src[end:]
body = body.replace("from .tools import tools", "from nodes.tools import tools")

out = "evaluation/runners/react_agent_recovered.py"
with open(out, "w", encoding="utf-8") as f:
    f.write(header + body)
print("written:", out)
