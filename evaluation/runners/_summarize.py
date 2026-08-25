import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
for r in data:
    if r.get("status") != "completed":
        print(f"{r['id']}: {r['status']}")
        continue
    exp = ",".join(r.get("expected_sequence") or r.get("expected_tools") or [])
    act = ",".join(r.get("actual_sequence") or [])
    fail = r.get("failure_type") or "PASS"
    llm = r.get("total_llm_calls", r.get("llm_calls", "?"))
    tools = r.get("total_tool_calls", r.get("tool_call_count", "?"))
    lat = r.get("total_latency_s", "?")
    print(f"{r['id']}: exp=[{exp}] act=[{act}] {fail} | planner={r.get('planner_calls','-')} llm={llm} tools={tools} lat={lat}s")
