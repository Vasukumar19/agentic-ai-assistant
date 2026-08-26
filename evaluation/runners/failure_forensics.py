"""Phase 11 Failure Forensics Analyzer.

Inspects baseline trace results (phase10_baseline_qwen3_results.json)
and generates failure forensics table.
"""

import json
from pathlib import Path


def main():
    res_path = Path("evaluation/results/phase10_baseline_qwen3_results.json")
    if not res_path.exists():
        print(f"File not found: {res_path}")
        return

    data = json.loads(res_path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    
    forensics = []
    for c in cases:
        status = c.get("execution_status")
        called = c.get("called_raw", [])
        expected_tools = c.get("expected_tools", [])
        expected_deps = c.get("expected_dependencies", [])
        
        # Determine failure category
        is_complete = status == "completed" and set(expected_tools).issubset(set(called))
        if is_complete:
            continue
            
        term_reason = status
        if status == "completed" and not set(expected_tools).issubset(set(called)):
            category = "PREMATURE_TERMINATION"
            term_reason = "planner stopped before calling all expected tools"
        elif status == "repeated_tool_call":
            category = "REPEATED_TOOL"
        elif status == "budget_exhausted":
            category = "BUDGET_EXHAUSTION"
        elif c.get("error"):
            category = "INFRASTRUCTURE"
        else:
            category = "TOOL_SELECTION_FAILURE"

        # Inspect last tool & evidence availability
        last_tool = called[-1] if called else "(none)"
        last_result = (c.get("answer_preview") or "")[:150]
        
        # Evidence of next step in result?
        evidence_available = len(expected_tools) > len(called)
        
        entry = {
            "case_id": c["id"],
            "query": c["question"],
            "expected_tools": expected_tools,
            "actual_tools": called,
            "last_tool": last_tool,
            "last_result_preview": last_result,
            "execution_status": status,
            "termination_reason": term_reason,
            "evidence_in_result": evidence_available,
            "category": category
        }
        forensics.append(entry)
        
    out_path = Path("evaluation/reports/phase11_failure_forensics.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    lines = [
        "# Phase 11 — Failure Forensics Analysis",
        "",
        f"Analyzed **{len(cases)}** baseline benchmark cases. Identified **{len(forensics)}** representative failure cases.",
        "",
        "| Case ID | Query | Expected Tools | Actual Tools | Last Tool | Execution Status | Category | Evidence in Result? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in forensics:
        exp_str = ", ".join(f["expected_tools"])
        act_str = ", ".join(f["actual_tools"]) or "(none)"
        q_trunc = f["query"][:40].replace("|", " ")
        lines.append(f"| `{f['case_id']}` | {q_trunc} | `{exp_str}` | `{act_str}` | `{f['last_tool']}` | `{f['execution_status']}` | **{f['category']}** | {'YES' if f['evidence_in_result'] else 'NO'} |")
        
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated failure forensics report: {out_path} ({len(forensics)} failure cases recorded)")


if __name__ == "__main__":
    main()
