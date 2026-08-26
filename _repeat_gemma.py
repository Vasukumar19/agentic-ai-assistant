"""Repeatability: 5 difficult 3-server cases run twice with Gemma 3 12B."""
import os, json, time
from pathlib import Path

os.environ["LLM_PROVIDER"] = "ollama"
os.environ["LLM_MODEL"] = "gemma3:12b"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_REASONING"] = "0"
os.environ["MAX_EXECUTION_STEPS"] = "10"
os.environ["MCP_SERVERS"] = json.dumps([
    {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
    {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
    {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
])

from graph import create_runnable_graph
from mcp_layer.registry import registry

registry._servers = {}
registry.load_servers_from_config()
registry.discover(force=True)

app = create_runnable_graph()

ids = ["p6c_41", "p6c_43", "p6c_46", "p6c_48", "p6c_50"]
cases = {c["id"]: c for c in json.loads(open("evaluation/datasets/phase6c_multiserver.json", encoding="utf-8").read())}

results = []
for cid in ids:
    q = cases[cid]["query"]
    for run_num in [1, 2]:
        print(f"Running {cid} run {run_num}...")
        t0 = time.perf_counter()
        try:
            out = app.invoke({"question": q})
            err = None
        except Exception as exc:
            out = {}
            err = str(exc)
        dt = int((time.perf_counter() - t0) * 1000)
        evs = out.get("trace_events") or []
        called_tools = [
            e["metadata"]["tool"]
            for e in evs
            if e["event_type"] in ("TOOL_CALL", "MCP_TOOL_CALL") and "tool" in e["metadata"]
        ]
        status = out.get("execution_status") if not err else "error"
        ans = (out.get("answer") or "")[:100]
        
        rec = {
            "case_id": cid,
            "run": run_num,
            "latency_ms": dt,
            "status": status,
            "tools": called_tools,
            "answer_preview": ans,
            "error": err,
        }
        results.append(rec)
        print(f"  {cid} run{run_num}: {dt}ms status={status} tools={called_tools} ans={ans!r}")

out_file = Path("evaluation/results/gemma3_repeatability.json")
out_file.parent.mkdir(parents=True, exist_ok=True)
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved repeatability results to {out_file}")
