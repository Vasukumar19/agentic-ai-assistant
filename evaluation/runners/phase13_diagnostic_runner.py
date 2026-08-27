"""Phase 13 Diagnostic Dataset Runner.

Runs the 40-case diagnostic dataset: evaluation/datasets/phase13_reliability_diagnostic.json
Measures:
- Multi-operation handling
- Premature termination recovery
- Argument repair attempts & recovery
- MCP server hardening against crashes
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    os.environ["MAX_EXECUTION_STEPS"] = "10"
    os.environ["PLANNING_STRATEGY"] = "hybrid"
    os.environ["DISCOVERY_STRATEGY"] = "none"
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["LLM_MODEL"] = "qwen3:8b"
    os.environ["OLLAMA_REASONING"] = "0"
    os.environ["RESULT_AWARE_REPLANNING"] = "on"
    os.environ["PLANNER_COMPLETION_CONTEXT"] = "on"
    os.environ["GOAL_FULFILLMENT_GUARD"] = "on"
    os.environ["MCP_ARGUMENT_REPAIR"] = "on"

    os.environ["MCP_SERVERS"] = json.dumps([
        {"name": "calendar", "transport": "stdio", "command": "python", "args": ["mcp_calendar_server.py"]},
        {"name": "notes", "transport": "stdio", "command": "python", "args": ["mcp_notes_server.py"]},
        {"name": "reminders", "transport": "stdio", "command": "python", "args": ["mcp_reminders_server.py"]},
        {"name": "filesystem", "transport": "stdio", "command": "python", "args": ["mcp_filesystem_server.py"]},
    ])

    from graph import create_runnable_graph
    from mcp_layer.registry import registry
    registry._servers = {}
    registry.load_servers_from_config()
    registry.discover(force=True)

    dataset_path = Path("evaluation/datasets/phase13_reliability_diagnostic.json")
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    out_path = Path("evaluation/results/phase13_diagnostic_results.json")

    app = create_runnable_graph()
    results = []

    print(f"Running 40 diagnostic cases with Full Reliability Guard + Repair + Hardening\n")

    for i, case in enumerate(cases, 1):
        cid, q, cat = case["id"], case["query"], case.get("category", "general")
        print(f"[{i:02d}/40] [{cat}] {cid}: {q[:40]!r} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            out = app.invoke({"question": q})
            dur = int((time.perf_counter() - t0) * 1000)
            evs = out.get("trace_events") or []
            called = [e["metadata"]["tool"] for e in evs
                      if e["event_type"] in ("TOOL_CALL", "MCP_TOOL_CALL") and "tool" in e["metadata"]]
            
            goal_checks = [e for e in evs if e["event_type"] == "GOAL_CHECK"]
            goal_incompletes = [e for e in evs if e["event_type"] == "GOAL_INCOMPLETE"]
            arg_repairs = [e for e in evs if e["event_type"] == "ARGUMENT_REPAIR"]
            
            r = {
                "id": cid, "category": cat, "question": q,
                "expected_tools": case.get("expected_tools", []),
                "called": called,
                "execution_status": out.get("execution_status"),
                "goal_check_count": len(goal_checks),
                "goal_incomplete_count": len(goal_incompletes),
                "argument_repair_count": len(arg_repairs),
                "had_errors": any(e.get("error") for e in evs),
                "answer_preview": (out.get("answer") or "")[:200],
                "latency_ms": dur,
                "events": len(evs),
            }
            results.append(r)
            print(f"-> {dur}ms tools={len(called)} guard_re-prompts={len(goal_incompletes)} rep={len(arg_repairs)} status={out.get('execution_status')}")
        except Exception as exc:
            dur = int((time.perf_counter() - t0) * 1000)
            print(f"ERROR {exc!r}")
            r = {"id": cid, "category": cat, "question": q, "error": str(exc)[:300], "latency_ms": dur}
            results.append(r)

    out_path.write_text(json.dumps({
        "dataset": "phase13_reliability_diagnostic.json",
        "total_cases": len(results),
        "cases": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved diagnostic results to {out_path}")


if __name__ == "__main__":
    main()
