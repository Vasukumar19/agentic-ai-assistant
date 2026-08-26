import json
import re
import time
import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from llm import llm
from config import MAX_TOOL_STEPS, TIMEOUT_LLM_S, LLM_PROVIDER, LLM_MODEL_OVERRIDE, MODEL_NAME

logger = logging.getLogger(__name__)

# Dynamic tool info via registry Ã¢â‚¬â€ keeps Planner agnostic to native vs MCP
def _get_registry():
    try:
        from mcp_layer.registry import registry
        return registry
    except Exception:
        return None

def _ensure_mcp_discovery():
    reg = _get_registry()
    if reg is None:
        return
    try:
        if not reg._discovered:
            # load from env/file if not already
            if not reg._servers:
                reg.load_servers_from_config()
            if reg._servers:
                reg.discover()
                # refresh tools global after discovery
                try:
                    from .tools import _refresh_tool_node
                    _refresh_tool_node()
                except Exception:
                    pass
    except Exception:
        pass

def _get_valid_names():
    _ensure_mcp_discovery()
    reg = _get_registry()
    if reg is not None:
        try:
            return reg.valid_names()
        except Exception:
            pass
    try:
        from .tools import tools as _tools
        return [t.name for t in _tools]
    except Exception:
        return ["web_search", "calculator"]

def _get_tool_info():
    _ensure_mcp_discovery()
    reg = _get_registry()
    if reg is not None:
        try:
            return reg.tool_info()
        except Exception:
            pass
    try:
        from .tools import tools as _tools
        return "\n".join([f"- {t.name}: {t.description}\n  Schema: {t.args_schema.model_json_schema() if t.args_schema else 'None'}" for t in _tools])
    except Exception:
        return "- web_search: Search the web\n- calculator: Evaluate expressions"

# keep legacy globals for external imports (but they are now dynamic)
def _legacy_tool_info():
    return _get_tool_info()
def _legacy_valid():
    return _get_valid_names()

TOOL_INFO = _legacy_tool_info()
VALID_TOOL_NAMES = _legacy_valid()

PLANNER_SYSTEM_PROMPT_TEMPLATE = """You are a precise, reliable multi-step execution planner.
Your job is to analyze the user's query, any retrieved context, and all previous tool executions, then decide the SINGLE next action.

Available Tools:
{tool_info}

MANDATORY RULES:
1. Action Selection: You may only output 'action': 'tool' OR 'action': 'final'.
2. Tool Necessity - Arithmetic & Calculations:
   - If the user query requires ANY arithmetic, percentage, ratio, difference, multiplication, division, power/sqrt, or numerical computation, you MUST call the 'calculator' tool.
   - NEVER do mental math or calculate in your head. Always execute the calculation with the 'calculator' tool.
3. Tool Necessity - External Facts & Real-Time Lookups:
   - If the query asks for real-world entities, current facts, statistics, prices, populations, or external info NOT provided in 'RETRIEVED CONTEXT', you MUST call the 'web_search' tool.
4. Multi-Step Execution & Dependency:
   - For multi-step queries (e.g. search population then calculate 0.5%, or search two entities and compare/subtract them, or retrieve policy then multiply for 3 employees), execute each tool step one at a time.
   - Use the output from earlier steps to supply arguments to subsequent steps.
5. Multi-Step Completion Checklist (BEFORE RETURNING 'final'):
   - Review the original user query. List every operation explicitly requested.
   - Check 'PREVIOUS TOOL EXECUTIONS'. Have all requested lookups and calculations been executed via tools?
   - If ANY requested calculation or lookup is missing, you MUST NOT return 'final'. You MUST output 'action': 'tool' for the next missing operation.
   - Only return 'final' when ALL required operations have been executed and you have all facts to answer completely.
6. Pure Context Queries:
   - If 'RETRIEVED CONTEXT' contains the exact information needed AND NO arithmetic/calculation/search was requested, return 'action': 'final'.
"""

class PlannerDecision(BaseModel):
    action: Literal["tool", "final"] = Field(description="Choose 'tool' to call a tool, or 'final' to provide the final answer.")
    tool: Optional[str] = Field(default=None, description=f"If action is 'tool', provide the exact name of the tool to call. Valid options: {VALID_TOOL_NAMES}")
    arguments: Optional[dict] = Field(default=None, description="If action is 'tool', provide a JSON object of arguments matching the tool's schema.")
    answer: Optional[str] = Field(default=None, description="If action is 'final', provide the final response to the user.")

# legacy alias for imports that expect PLANNER_SYSTEM_PROMPT
PLANNER_SYSTEM_PROMPT = PLANNER_SYSTEM_PROMPT_TEMPLATE.format(tool_info=TOOL_INFO)

def check_completion_guard(question: str, completed_steps: list[str], tool_results: list[dict], context: str) -> tuple[bool, str]:
    q_lower = question.lower()
    calc_indicators = [
        "calculate", "multiply", "multiplied", "divide", "divided", "sum of",
        "subtract", "square root", "sqrt", "%", "percent", "ratio of", "ratio", "difference in",
        "difference between", "how much would", "how many are left", "have left", "remaining",
        "total amount if", "what is that divided", "what would", "times larger", "within budget",
        "difference", "in total", "stipend for", "team of"
    ]
    math_op_regex = re.search(r'\b\d+\s*[\+\-\*\/]\s*\d+\b', question)
    requires_calc = any(ind in q_lower for ind in calc_indicators) or bool(math_op_regex)
    if requires_calc and "calculator" not in completed_steps:
        return False, "Calculation requested in query has not been executed via calculator tool."
    search_indicators = [
        "who is", "what is the population", "current price", "stock price", "current ceo",
        "gdp of", "speed of light", "distance to", "distance from", "tallest building",
        "population of", "latest news", "release date", "retail price"
    ]
    requires_search = any(ind in q_lower for ind in search_indicators)
    has_retrieved_info = bool(context and len(context.strip()) > 30) or ("rag" in completed_steps) or ("web_search" in completed_steps)
    if requires_search and not has_retrieved_info:
        return False, "External factual lookup requested in query has not been executed via web_search tool."
    return True, ""

def is_repeated_tool_call(tool_name: str, tool_args: dict, tool_results: list[dict]) -> bool:
    if not tool_results:
        return False
    last_exec = tool_results[-1]
    if last_exec.get("tool") == tool_name and last_exec.get("arguments") == tool_args:
        return True
    return False


def _record_call_history(state: dict, tool_name: str, tool_args: dict, result) -> None:
    """Phase 8 — maintain call-signature history for state-aware loop detection."""
    import json as _json
    try:
        sig = _json.dumps({"t": tool_name, "a": tool_args}, sort_keys=True)
        hist = state.get("tool_call_history")
        if hist is None:
            hist = []
        hist.append({"sig": sig, "result": str(result or "")[:500]})
        state["tool_call_history"] = hist[-20:]
    except Exception:
        pass


def detect_loop(history: list[dict], tool_name: str, tool_args: dict, tool_results: list[dict]) -> str | None:
    """State-aware loop detection over full call history.

    Returns loop kind or None:
      - 'alternating_identical': same (tool,args) executed >=2 times before with
        unchanged results -> meaningful repetition absent.
      - None otherwise. Repeated tool names with changed args/results are allowed.
    """
    import json as _json
    try:
        sig = _json.dumps({"t": tool_name, "a": tool_args}, sort_keys=True)
    except Exception:
        return None
    prior = [h for h in history if h.get("sig") == sig]
    if len(prior) < 2:
        return None
    # results unchanged across prior executions -> no new information possible
    results = {str(h.get("result", ""))[:200] for h in prior}
    ok_results = {r for r in results if not r.lower().startswith("error")}
    if len(results) == 1 or len(ok_results) <= 1:
        return "alternating_identical"
    return None

def _emit_planner_event(state: dict, dur_ms: int, decision: PlannerDecision | None, step: int, status: str = "success", extra: dict | None = None, error: dict | None = None):
    try:
        from observability.trace import make_event, append_event, add_latency, extract_llm_usage
        add_latency(state, "planner", dur_ms)
        meta = extra or {}
        meta.update({"planner_step": step, "latency_ms": dur_ms,
                     "provider": LLM_PROVIDER or "unknown", "model": LLM_MODEL_OVERRIDE or MODEL_NAME})
        if decision is not None:
            meta.update({"action": decision.action, "tool": decision.tool, "arguments": decision.arguments,
                         "answer_preview": (decision.answer or "")[:200] if decision.answer else None})
        ev = make_event(state, "PLANNER", "planner", duration_ms=dur_ms, status=status, metadata=meta, error=error)
        append_event(state, ev)
    except Exception:
        pass

def _emit_plan_event(state, ev_type, meta, status="success", error=None):
    try:
        from observability.trace import make_event, append_event
        ev = make_event(state, ev_type, "planner", status=status, metadata=meta, error=error)
        append_event(state, ev)
    except Exception:
        pass


def _dependency_planner(state: dict, level_cap: int = 1, allow_replan: bool = False,
                        dedupe: bool = False, complexity: str = "") -> dict | None:
    """Strategy B Ã¢â‚¬â€ generate/validate a structured plan once, then execute
    dependency-ready steps deterministically (no per-step LLM call).
    Returns None to fall back to baseline behavior for non-research paths.
    level_cap: 0=baseline-only, 1=dependency planning, 2=replan escalation allowed."""
    from config import PLANNING_STRATEGY, MAX_PLAN_STEPS, TIMEOUT_LLM_S, MAX_REPLANS
    if PLANNING_STRATEGY not in ("dependency", "hybrid"):
        return None
    if PLANNING_STRATEGY == "dependency" and (level_cap < 1 or allow_replan or dedupe):
        # pure Phase-7 dependency run must stay byte-for-byte behavior-compatible
        level_cap, allow_replan, dedupe = 1, False, False
    route = state.get("route", "research_query")
    if route not in ("research_query", ""):
        return None

    import time as _t
    from pydantic import ValidationError as PydValidationError
    from langchain_core.messages import AIMessage
    from planning.schema import Plan
    from planning.validation import validate_plan, next_ready_steps, plan_complete
    from observability.timeout import run_with_timeout

    question = state.get("question", "")
    context = state.get("_combined_context", "")
    messages = state.get("messages", [])
    tool_call_count = state.get("tool_call_count", 0)
    completed_steps = list(state.get("completed_steps", []))
    tool_results = list(state.get("tool_results", []))

    # sync last tool result into plan state
    active_plan_data = state.get("active_plan")
    done: set[str] = set(state.get("plan_completed_steps") or [])
    step_results: dict = dict(state.get("plan_step_results") or {})
    invalid_count = int(state.get("plan_invalid_count") or 0)
    dup_guard: dict = dict(state.get("_dup_guard") or {})
    pending_step = state.get("pending_step_id")

    pending_step_result = None
    if messages and messages[-1].type == "tool" and len(messages) >= 2 and messages[-2].type == "ai":
        result_content = messages[-1].content
        if pending_step and active_plan_data:
            pending_step_result = (pending_step, str(result_content))
            # record success signature for duplicate prevention
            if not str(result_content).lower().startswith("error"):
                prev = messages[-2]
                if getattr(prev, "tool_calls", None):
                    call = prev.tool_calls[0]
                    import json as _sj
                    dup_guard[_sj.dumps({"t": call["name"], "a": call["args"]}, sort_keys=True)] = pending_step
        else:
            # fallback: record into generic history
            prev = messages[-2]
            if getattr(prev, "tool_calls", None):
                call = prev.tool_calls[0]
                if len(tool_results) < tool_call_count:
                    completed_steps.append(call["name"])
                    tool_results.append({"tool": call["name"], "arguments": call["args"], "result": result_content})
                    _record_call_history(state, call["name"], call["args"], result_content)

    # Ã¢â€â‚¬Ã¢â€â‚¬ no plan yet Ã¢â€ â€™ generate + validate Ã¢â€â‚¬Ã¢â€â‚¬
    if not active_plan_data:
        valid_names = _get_valid_names()
        tool_info = _get_tool_info()
        plan_prompt = f"""You are a precise multi-step task planner.
Decompose the user's goal into an ordered plan using ONLY the available tools.

Available Tools:
{tool_info}

Rules:
- Use only tools from Available Tools (exact names).
- arguments must match each tool's schema. Do not invent values that must come from another step's output;
  instead declare depends_on so the value can be resolved at execution time.
- Keep it minimal: only steps required by the goal.
- Max {MAX_PLAN_STEPS} steps.

User Goal: {question}
"""
        if context:
            plan_prompt += f"\nRetrieved Context:\n{context[:2000]}\n"

        structured_llm = llm.with_structured_output(Plan)
        t0 = _t.perf_counter()
        try:
            def _call():
                return run_with_timeout(lambda: structured_llm.invoke([HumanMessage(content=plan_prompt)]), TIMEOUT_LLM_S)
            plan = _call()
        except Exception as e:
            _emit_planner_event(state, int((_t.perf_counter() - t0) * 1000), None, 1, status="error",
                                extra={"strategy": "dependency", "validation_result": f"plan_generation_failed: {str(e)[:200]}"})
            return {"answer": "I couldn't construct a valid plan for this request.",
                    "execution_status": "error",
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}

        # cap steps
        if len(plan.steps) > MAX_PLAN_STEPS:
            plan.steps = plan.steps[:MAX_PLAN_STEPS]

        def _confirm(tool, args):
            try:
                from mcp_layer.registry import registry
                return registry.requires_confirmation(tool, args)
            except Exception:
                return False

        validation = validate_plan(plan, valid_names, confirmation_required=_confirm)
        _emit_plan_event(state, "PLANNER", {"strategy": "dependency", "phase": "plan_created",
                                            "valid": validation.valid,
                                            "steps": [{"id": s.id, "tool": s.tool, "depends_on": s.depends_on} for s in plan.steps],
                                            "errors": validation.errors},
                          status="success" if validation.valid else "error")
        if not validation.valid:
            invalid_count += 1
            if invalid_count <= 2:
                # one revision attempt with errors fed back
                repair_prompt = plan_prompt + f"\n\nYour previous plan was INVALID:\n" + "\n".join(validation.errors) + \
                    "\nReturn a corrected plan."
                try:
                    plan = run_with_timeout(lambda: llm.with_structured_output(Plan).invoke(
                        [HumanMessage(content=repair_prompt)]), TIMEOUT_LLM_S)
                    if len(plan.steps) > MAX_PLAN_STEPS:
                        plan.steps = plan.steps[:MAX_PLAN_STEPS]
                    validation = validate_plan(plan, valid_names, confirmation_required=_confirm)
                    _emit_plan_event(state, "PLANNER", {"strategy": "dependency", "phase": "plan_repaired",
                                                        "valid": validation.valid, "errors": validation.errors},
                                      status="success" if validation.valid else "error")
                except Exception:
                    pass
            if not validation.valid:
                return {"answer": "I couldn't construct a valid plan: " + "; ".join(validation.errors[:3]),
                        "execution_status": "error", "plan_invalid_count": invalid_count, "plan_replans": int(state.get("plan_replans") or 0), "_dup_guard": dup_guard,
                        "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                        "latency_breakdown": state.get("latency_breakdown")}

        return {
            "active_plan": plan.model_dump(),
            "plan_completed_steps": [],
            "plan_step_results": {},
            "plan_invalid_count": invalid_count, "plan_replans": int(state.get("plan_replans") or 0), "_dup_guard": dup_guard,
            "execution_status": "running",
            "completed_steps": completed_steps,
            "tool_results": tool_results,
            "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
            "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage"),
        }

    # Ã¢â€â‚¬Ã¢â€â‚¬ plan exists Ã¢â€ â€™ execute Ã¢â€â‚¬Ã¢â€â‚¬
    plan = Plan(**active_plan_data)
    if pending_step_result:
        sid, res = pending_step_result
        done.add(sid)
        step_results[sid] = res
        failed = isinstance(res, str) and res.lower().startswith("error")
    else:
        failed = False

    steps_by_id = {s.id: s for s in plan.steps}
    ready = next_ready_steps(plan, done)

    if not ready or failed:
        if plan_complete(plan, done) and not failed:
            # compose final answer from step results
            results_txt = "\n".join(f"- {sid} ({steps_by_id[sid].tool}): {(step_results.get(sid,'') or '')[:400]}"
                                    for sid in (s.id for s in plan.steps))
            final_prompt = f"""User Goal: {question}

Executed plan step results:
{results_txt}

Compose a concise final answer for the user's goal using ONLY these results."""
            try:
                ans = run_with_timeout(lambda: llm.invoke([HumanMessage(content=final_prompt)]), TIMEOUT_LLM_S)
                answer = ans.content
            except Exception:
                answer = "Task steps executed but I couldn't compose the summary."
            return {"answer": answer, "last_action": "final", "execution_status": "completed",
                    "active_plan": state.get("active_plan"), "plan_completed_steps": sorted(done),
                    "plan_step_results": step_results, "plan_invalid_count": invalid_count, "plan_replans": int(state.get("plan_replans") or 0), "_dup_guard": dup_guard,
                    "completed_steps": completed_steps, "tool_results": tool_results,
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}
        # failure mid-plan: hybrid may escalate to a state-aware replan within budget
        replans = int(state.get("plan_replans") or 0)
        if allow_replan and failed and replans < MAX_REPLANS and ready is not None:
            failed_sid = pending_step_result[0] if pending_step_result else None
            remaining = [s for s in plan.steps if s.id not in done]
            replan_prompt = f"""You are re-planning after a failure.

Original Goal: {question}
Completed Steps (do NOT repeat these): {[s for s in done]}
Failed Step: {failed_sid} with result: {(pending_step_result[1] if pending_step_result else '')[:300] if pending_step_result else 'unknown'}
Remaining Steps: {[{'id': s.id, 'tool': s.tool, 'purpose': s.purpose} for s in remaining]}

Available Tools:
{_get_tool_info()}

Return a corrected plan for the REMAINING work only. Do not repeat completed steps."""
            try:
                new_plan = run_with_timeout(lambda: llm.with_structured_output(Plan).invoke(
                    [HumanMessage(content=replan_prompt)]), TIMEOUT_LLM_S)
                v2 = validate_plan(new_plan, _get_valid_names())
                _emit_plan_event(state, "PLANNER", {"strategy": "hybrid", "phase": "replan",
                                                    "replans": replans + 1, "valid": v2.valid,
                                                    "errors": v2.errors[:3]},
                                  status="success" if v2.valid else "error")
                if v2.valid and len(new_plan.steps) <= MAX_PLAN_STEPS:
                    return {
                        "active_plan": new_plan.model_dump(),
                        "plan_completed_steps": [],   # fresh DAG relative to remaining work
                        "plan_step_results": {},
                        "plan_replans": replans + 1,
                        "plan_invalid_count": invalid_count, "plan_replans": int(state.get("plan_replans") or 0), "_dup_guard": dup_guard,
                        "execution_status": "running",
                        "completed_steps": completed_steps,
                        "tool_results": tool_results,
                        "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                        "latency_breakdown": state.get("latency_breakdown"),
                    }
            except Exception:
                pass
        # failure mid-plan or stuck: fall back to baseline LLM decision with plan context
        _emit_plan_event(state, "PLANNER", {"strategy": "dependency", "phase": "fallback_to_baseline",
                                            "failed": failed, "ready": ready}, status="error")
        return None

    step = steps_by_id[ready[0]]
    args = dict(step.arguments or {})
    # dependency data propagation: substitute placeholders like "{s1}" with prior results
    for k, v in list(args.items()):
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            ref = v[1:-1]
            if ref in step_results:
                args[k] = step_results[ref]
            elif ref.split(".")[0] in step_results:
                base = step_results[ref.split(".")[0]]
                args[k] = f"{base}"  # planner-level resolution; keep raw if field missing

    # duplicate-call prevention: skip identical successful (tool,args) already executed
    if dedupe:
        import json as _json
        sig = _json.dumps({"t": step.tool, "a": args}, sort_keys=True)
        seen_ok = state.get("_dup_guard") or {}
        if sig in seen_ok:
            prev_sid = seen_ok[sig]
            done.add(step.id)
            step_results[step.id] = step_results.get(prev_sid, "")
            _emit_plan_event(state, "PLANNER", {"strategy": "hybrid", "phase": "duplicate_prevented",
                                                "step_id": step.id, "same_as": prev_sid})
            nxt = next_ready_steps(plan, done)
            if not nxt:
                # everything done Ã¢â€ â€™ compose final
                results_txt = "\n".join(f"- {sid}: {(step_results.get(sid,'') or '')[:300]}"
                                        for sid in steps_by_id)
                try:
                    ans = run_with_timeout(lambda: llm.invoke([HumanMessage(
                        content=f"User Goal: {question}\nResults:\n{results_txt}\nCompose a concise final answer.")]),
                        TIMEOUT_LLM_S)
                    answer = ans.content
                except Exception:
                    answer = "Task completed."
                return {"answer": answer, "last_action": "final", "execution_status": "completed",
                        "active_plan": state.get("active_plan"), "plan_completed_steps": sorted(done),
                        "plan_step_results": step_results, "plan_invalid_count": invalid_count, "plan_replans": int(state.get("plan_replans") or 0), "_dup_guard": dup_guard,
                        "completed_steps": completed_steps, "tool_results": tool_results,
                        "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                        "latency_breakdown": state.get("latency_breakdown")}
            step = steps_by_id[nxt[0]]
            args = dict(step.arguments or {})

    _emit_plan_event(state, "PLANNER", {"strategy": "dependency" if PLANNING_STRATEGY == "dependency" else "hybrid",
                                        "phase": "step_ready",
                                        "step_id": step.id, "tool": step.tool, "depends_on": step.depends_on})

    tool_call_id = f"call_{tool_call_count}"
    ai_msg = AIMessage(content="", tool_calls=[{"name": step.tool, "args": args, "id": tool_call_id}])
    return {
        "messages": [ai_msg],
        "current_step": step.tool,
        "last_action": step.tool,
        "tool_call_count": tool_call_count + 1,
        "execution_status": "running",
        "pending_step_id": step.id,
        "active_plan": state.get("active_plan"),
        "plan_completed_steps": sorted(done),
        "plan_step_results": step_results,
        "plan_invalid_count": invalid_count, "plan_replans": int(state.get("plan_replans") or 0), "_dup_guard": dup_guard,
        "completed_steps": completed_steps,
        "tool_results": tool_results,
        "execution_trace": list(state.get("execution_trace", [])),
        "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
        "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage"),
    }


def _hybrid_route(state: dict) -> dict | None:
    """Phase 7B adaptive hybrid — classify complexity, escalate planning depth only when justified."""
    from config import PLANNING_STRATEGY, HYBRID_LEVEL_CAP, HYBRID_REPLAN
    if PLANNING_STRATEGY != "hybrid":
        return None
    # mid-plan continuations route straight into the dependency executor
    if state.get("active_plan") or state.get("pending_step_id"):
        return _dependency_planner(state, level_cap=min(HYBRID_LEVEL_CAP, 2),
                                   allow_replan=HYBRID_REPLAN, dedupe=True)
    route = state.get("route", "research_query")
    if route not in ("research_query", ""):
        return None

    from planning.classifier import classify_complexity
    valid_names = _get_valid_names()
    cls = classify_complexity(state.get("question", ""), valid_names)

    if HYBRID_LEVEL_CAP == 0:
        level = 0
    elif cls == "MULTI_STEP":
        level = min(HYBRID_LEVEL_CAP, 2)
    elif cls in ("DEPENDENT", "UNCERTAIN"):
        level = min(HYBRID_LEVEL_CAP, 1)
    else:
        level = 0

    try:
        _emit_plan_event(state, "PLANNER", {"strategy": "hybrid", "phase": "classified",
                                            "complexity": cls, "planning_level": level,
                                            "level_cap": HYBRID_LEVEL_CAP})
    except Exception:
        pass

    if level >= 1:
        return _dependency_planner(state, level_cap=level,
                                   allow_replan=(HYBRID_REPLAN and level >= 2),
                                   dedupe=True, complexity=cls)
    return None  # SIMPLE → baseline path


def planner_node(state: dict) -> dict:
    # Phase 7/7B: strategy routing
    if state.get("_strategy") is None:
        from config import PLANNING_STRATEGY as _PS
        state["_strategy"] = _PS
    if state["_strategy"] == "hybrid":
        dep = _hybrid_route(state)
    else:
        dep = _dependency_planner(state)
    if dep is not None:
        return dep

    t_start = time.perf_counter()
    question = state.get("question", "")
    context = state.get("_combined_context", "")
    messages = state.get("messages", [])
    
    tool_call_count = state.get("tool_call_count", 0)
    completed_steps = list(state.get("completed_steps", []))
    tool_results = list(state.get("tool_results", []))
    execution_trace = list(state.get("execution_trace", []))
    
    retrieval_plan = state.get("retrieval_plan", {})
    if retrieval_plan.get("rag") and "rag" not in completed_steps:
        completed_steps.insert(0, "rag")
    if (retrieval_plan.get("profile") or retrieval_plan.get("semantic")) and "memory_search" not in completed_steps:
        completed_steps.insert(0, "memory_search")

    if context:
        user_prompt = f"RETRIEVED CONTEXT:\n{context}\n\nUser Query: {question}"
    else:
        user_prompt = f"User Query: {question}"
        
    if messages and messages[-1].type == "tool":
        last_tool_msg = messages[-1]
        if len(messages) >= 2 and messages[-2].type == "ai":
            last_ai_msg = messages[-2]
            if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
                call = last_ai_msg.tool_calls[0]
                tool_name = call["name"]
                tool_args = call["args"]
                if len(tool_results) < tool_call_count:
                    if tool_name not in completed_steps or completed_steps.count(tool_name) < tool_call_count:
                        completed_steps.append(tool_name)
                    tool_results.append({"tool": tool_name, "arguments": tool_args, "result": last_tool_msg.content})
                    _record_call_history(state, tool_name, tool_args, last_tool_msg.content)

    if tool_results:
        history_str = "PREVIOUS TOOL EXECUTIONS:\n"
        for i, res in enumerate(tool_results):
            history_str += f"\nStep {i+1}: Called '{res.get('tool')}'\n"
            history_str += f"Arguments: {json.dumps(res.get('arguments', {}))}\n"
            history_str += f"Result: {res.get('result', 'Error/No Result')}\n"
        user_prompt = f"{history_str}\n\n{user_prompt}"

    # Phase 7 Strategy C (replan): expose explicit planning state
    from config import PLANNING_STRATEGY
    if PLANNING_STRATEGY == "replan":
        failed_results = [r for r in tool_results if str(r.get("result", "")).lower().startswith("error")]
        state_txt = "\n".join(f"- {r.get('tool')}: {str(r.get('result',''))[:200]}" for r in tool_results)
        failed_txt = "\n".join(f"- {r.get('tool')}: {str(r.get('result',''))[:150]}" for r in failed_results) or "(none)"
        user_prompt = f"""[PLANNING STATE]
Original Goal: {question}
Completed Steps: {', '.join(completed_steps) or '(none)'}
Available State (tool outputs so far):
{state_txt or '(none)'}
Failed Steps:
{failed_txt}
Remaining Goal: achieve the original goal using what is still missing.

Decide the SINGLE next action that makes progress on the Remaining Goal.

{user_prompt}"""

    # dynamic prompt per-request (registry may have new MCP tools)
    _prompt = PLANNER_SYSTEM_PROMPT_TEMPLATE.format(tool_info=_get_tool_info())
    structured_llm = llm.with_structured_output(PlannerDecision)

    t_llm_start = time.perf_counter()
    try:
        from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
        def _call_llm():
            return structured_llm.invoke([SystemMessage(content=_prompt), HumanMessage(content=user_prompt)])
        try:
            decision = run_with_timeout(_call_llm, TIMEOUT_LLM_S)
        except ObsTimeout as te:
            t_llm_end = time.perf_counter()
            llm_latency = round(t_llm_end - t_llm_start, 3)
            execution_trace.append({"step": "planner_error", "latency_s": llm_latency, "error": str(te)})
            try:
                from observability.errors import make_error_payload, ErrorType
                from observability.trace import make_event, append_event
                err = make_error_payload(ErrorType.TIMEOUT_ERROR.value, "planner", str(te), trace_id=state.get("trace_id"))
                ev = make_event(state, "TIMEOUT", "planner", duration_ms=int(llm_latency*1000), status="timeout",
                                metadata={"timeout_s": TIMEOUT_LLM_S}, error=err)
                append_event(state, ev)
                _emit_planner_event(state, int(llm_latency*1000), None, tool_call_count+1, status="timeout",
                                    extra={"validation_result": "timeout", "error": str(te)[:300]}, error=err)
            except Exception:
                pass
            return {"answer": "I'm sorry, the planner timed out while thinking. Please try again.",
                    "execution_status": "timeout", "execution_trace": execution_trace,
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}
    except Exception as e:
        t_llm_end = time.perf_counter()
        logger.error(f"Planner failed to generate structured output: {e}")
        execution_trace.append({"step": "planner_error", "latency_s": round(t_llm_end - t_llm_start, 3), "error": str(e)})
        try:
            from observability.errors import classify_error, make_error_payload
            err_type = classify_error(e, component="planner")
            err = make_error_payload(err_type, "planner", str(e), trace_id=state.get("trace_id"))
            _emit_planner_event(state, int((t_llm_end - t_llm_start)*1000), None, tool_call_count+1, status="error",
                                extra={"validation_result": "error", "error": str(e)[:300]}, error=err)
        except Exception:
            pass
        return {"answer": "I'm sorry, I encountered an internal error while planning the next step.",
                "execution_status": "error", "execution_trace": execution_trace,
                "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                "latency_breakdown": state.get("latency_breakdown")}
    t_llm_end = time.perf_counter()
    llm_latency = round(t_llm_end - t_llm_start, 3)

    # record llm usage
    try:
        from observability.trace import extract_llm_usage
        # decision is a Pydantic object; the raw response is not captured, but we estimate
        if state.get("llm_usage") is None:
            state["llm_usage"] = []
        # try to capture from structured output Ã¢â‚¬â€ not always available, use placeholder
        state["llm_usage"].append({"node": "planner", "provider": LLM_PROVIDER or "unknown",
                                   "model": LLM_MODEL_OVERRIDE or MODEL_NAME,
                                   "latency_ms": int(llm_latency*1000), "step": tool_call_count+1})
    except Exception:
        pass

    if decision.action == "tool":
        # Phase 8: state-aware alternating-loop detection.
        # A→A (identical sig) and A→B→A→B (same sigs recurring with unchanged
        # results) terminate; a repeated tool whose inputs/results changed is allowed.
        loop_kind = detect_loop(tool_call_history, decision.tool, decision.arguments or {}, tool_results)
        if loop_kind is None and is_repeated_tool_call(decision.tool, decision.arguments or {}, tool_results):
            loop_kind = "consecutive_identical"
        if loop_kind:
            logger.warning(f"Loop detected ({loop_kind}): {decision.tool} with {decision.arguments}")
            execution_trace.append({"step": f"planner_{tool_call_count+1}", "decision": f"loop_detected_{loop_kind}", "llm_latency_s": llm_latency})
            _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="error",
                                extra={"validation_result": f"loop_detected_{loop_kind}",
                                       "termination_reason": "loop_detected",
                                       "loop_detected": True, "loop_kind": loop_kind})
            return {"answer": "Task terminated to prevent repeated execution of the same operation without new information.",
                    "execution_status": "repeated_tool_call", "tool_loop_detected": True,
                    "completed_steps": completed_steps, "tool_results": tool_results,
                    "execution_trace": execution_trace,
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage")}

    if decision.action == "final":
        is_complete, guard_reason = check_completion_guard(question, completed_steps, tool_results, context)
        if not is_complete and tool_call_count < MAX_TOOL_STEPS:
            logger.info(f"Completion guard triggered: {guard_reason}. Prompting planner for missing step.")
            guard_prompt = f"{user_prompt}\n\n[GUARD NOTICE]: You attempted to finalize the task, but: {guard_reason}. You MUST execute the required tool first."
            try:
                from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
                def _call_guard():
                    return structured_llm.invoke([SystemMessage(content=_prompt), HumanMessage(content=guard_prompt)])
                try:
                    decision = run_with_timeout(_call_guard, TIMEOUT_LLM_S)
                except ObsTimeout:
                    pass
                else:
                    # record guard as validation
                    try:
                        _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="success",
                                            extra={"validation_result": f"guard_triggered: {guard_reason}", "guard_reason": guard_reason})
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Planner re-prompt failed: {e}")

    if decision.action == "tool":
        if decision.tool not in _get_valid_names():
            logger.warning(f"Planner hallucinated tool: {decision.tool}")
            try:
                from observability.errors import make_error_payload, ErrorType
                err = make_error_payload(ErrorType.TOOL_SELECTION_ERROR.value, "planner",
                                         f"hallucinated tool {decision.tool}", trace_id=state.get("trace_id"))
                _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="error",
                                    extra={"validation_result": "invalid_tool"}, error=err)
            except Exception:
                pass
            return {"answer": f"I tried to use an invalid tool: {decision.tool}. I cannot complete the request.",
                    "execution_status": "error", "execution_trace": execution_trace,
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}
            
        tool_call_id = f"call_{tool_call_count}"
        tool_call = {"name": decision.tool, "args": decision.arguments or {}, "id": tool_call_id}
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        execution_trace.append({"step": f"planner_{tool_call_count+1}", "action": "tool", "tool": decision.tool, "arguments": decision.arguments, "llm_latency_s": llm_latency})
        _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="success",
                            extra={"validation_result": "ok"})
        new_state = {"messages": [ai_msg], "current_step": decision.tool, "last_action": decision.tool,
                     "tool_call_count": tool_call_count + 1, "execution_status": "running",
                     "completed_steps": completed_steps, "tool_results": tool_results,
                     "execution_trace": execution_trace,
                     "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                     "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage")}
        return new_state
        
    else:
        answer = decision.answer or "Task complete."
        execution_trace.append({"step": f"planner_{tool_call_count+1}", "action": "final", "llm_latency_s": llm_latency})
        _emit_planner_event(state, int(llm_latency*1000), decision, tool_call_count+1, status="success",
                            extra={"validation_result": "final"})
        new_state = {"messages": [AIMessage(content=answer)], "answer": answer, "last_action": "final",
                     "execution_status": "completed", "completed_steps": completed_steps,
                     "tool_results": tool_results, "execution_trace": execution_trace,
                     "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                     "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage")}
        return new_state

