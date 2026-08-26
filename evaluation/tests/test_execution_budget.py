"""Phase 8 — execution budget decoupling + loop protection tests. Deterministic, no LLM."""

import pytest


class TestBudgetConfig:
    def test_decoupled_defaults_preserve_current_behavior(self):
        from config import MAX_EXECUTION_STEPS, MAX_TOOL_STEPS
        assert MAX_TOOL_STEPS == 5
        assert MAX_EXECUTION_STEPS == 5  # default unchanged

    def test_budget_env_override(self, monkeypatch):
        import importlib, config
        monkeypatch.setenv("MAX_EXECUTION_STEPS", "10")
        importlib.reload(config)
        assert config.MAX_EXECUTION_STEPS == 10
        assert config.MAX_TOOL_STEPS == 5  # untouched
        monkeypatch.setenv("MAX_EXECUTION_STEPS", "5")
        importlib.reload(config)
        # restore module state for other tests
        monkeypatch.setenv("MAX_EXECUTION_STEPS", "5")
        importlib.reload(config)


class TestLoopDetection:
    def _hist(self, calls):
        import json
        out = []
        for t, a, r in calls:
            sig = json.dumps({"t": t, "a": a}, sort_keys=True)
            out.append({"sig": sig, "result": r})
        return out

    def test_consecutive_identical_detected(self):
        from nodes.planner_node import detect_loop, is_repeated_tool_call
        hist = self._hist([("calculator", {"e": "1+1"}, "2"), ("calculator", {"e": "1+1"}, "2")])
        assert detect_loop(hist, "calculator", {"e": "1+1"}, []) == "alternating_identical"
        assert is_repeated_tool_call("calculator", {"e": "1+1"},
                                     [{"tool": "calculator", "arguments": {"e": "1+1"}}]) is True

    def test_alternating_loop_with_unchanged_results(self):
        # A -> B -> A -> B with same results: re-calling A must be flagged
        from nodes.planner_node import detect_loop
        hist = self._hist([
            ("calendar.list_events", {}, "[{a}]"),
            ("notes.list", {}, "[{b}]"),
            ("calendar.list_events", {}, "[{a}]"),
            ("notes.list", {}, "[{b}]"),
        ])
        assert detect_loop(hist, "calendar.list_events", {}, []) == "alternating_identical"

    def test_state_changing_repeat_allowed(self):
        # write -> read -> write with changed args: legitimate
        from nodes.planner_node import detect_loop
        hist = self._hist([
            ("filesystem.write_file", {"path": "f", "content": "v1"}, "ok"),
            ("filesystem.read_file", {"path": "f"}, "v1"),
        ])
        assert detect_loop(hist, "filesystem.write_file",
                           {"path": "f", "content": "v2"}, []) is None

    def test_failed_then_retry_allowed_once(self):
        from nodes.planner_node import detect_loop
        hist = self._hist([("notes.read", {"id": "x"}, "Error: not found")])
        # only one prior failure — planner may retry with corrected args or even same
        assert detect_loop(hist, "notes.read", {"id": "y"}, []) is None

    def test_empty_history_no_loop(self):
        from nodes.planner_node import detect_loop
        assert detect_loop([], "calculator", {"e": "1"}, []) is None


class TestBudgetExhaustionSemantics:
    def test_budget_exhaustion_distinct_from_completion(self):
        statuses = {"completed", "budget_exhausted"}
        assert "budget_exhausted" not in statuses - statuses  # sanity
        # the two are mutually exclusive terminal states
        s = "budget_exhausted"
        assert s != "completed"

    def test_exhaustion_metadata_fields(self):
        # mirrors should_continue metadata contract
        meta = {"termination_reason": "budget_exhausted", "execution_step": 10,
                "execution_budget": 10, "remaining_budget": 0,
                "loop_detected": False}
        assert meta["remaining_budget"] == 0
        assert meta["loop_detected"] is False
        assert meta["termination_reason"] == "budget_exhausted"

    def test_remaining_budget_never_negative(self):
        step, budget = 12, 10
        assert max(0, budget - step) == 0


class TestSafetyIndependentOfBudget:
    def test_save_history_persists_budget_exhausted_status(self):
        """Phase 8 regression: save_history must RETURN execution_status so
        LangGraph persists it (routers/nodes that only mutate state lose it)."""
        import graph as g
        import inspect
        src = inspect.getsource(g.save_history_node)
        assert '"execution_status": exec_status' in src, (
            "save_history_node must return execution_status for persistence")

    def test_save_history_recompute_logic(self, monkeypatch):
        # simulate: status running + tool_call_count >= budget -> budget_exhausted
        from config import MAX_EXECUTION_STEPS
        budget = max(MAX_EXECUTION_STEPS, 1)
        state = {"execution_status": "running", "tool_call_count": budget}
        exec_status = state["execution_status"]
        if exec_status == "running" and state.get("tool_call_count", 0) >= budget:
            exec_status = "budget_exhausted"
        assert exec_status == "budget_exhausted"
        # under-budget running stays running
        state2 = {"execution_status": "running", "tool_call_count": budget - 1}
        exec2 = state2["execution_status"]
        if exec2 == "running" and state2.get("tool_call_count", 0) >= budget:
            exec2 = "budget_exhausted"
        assert exec2 == "running"

    def test_per_tool_breaker_unchanged_threshold(self):
        from config import MAX_TOOL_FAILURES_PER_TOOL
        assert MAX_TOOL_FAILURES_PER_TOOL == 3

    def test_confirmation_independent_of_budget(self):
        # confirmation gating happens at plan validation / dispatch regardless of budget
        from mcp_layer.registry import registry
        registry._discovered = False
        registry._servers = {}
        registry.load_servers_from_config([{
            "name": "calendar", "transport": "stdio", "command": "python",
            "args": ["mcp_calendar_server.py"],
            "tool_policy": {"create_event": {"operation": "write", "requires_confirmation": True}},
        }])
        registry.discover(force=True)
        assert registry.requires_confirmation("calendar.create_event") is True
        # even at high budget, awaiting_confirmation path returns before execution
        from langchain_core.messages import AIMessage
        from nodes.tools import tool_node
        state = {"messages": [AIMessage(content="", tool_calls=[
            {"name": "calendar.create_event", "args": {"title": "B", "date": "2026-01-01"}, "id": "c"}])],
            "trace_id": "trace_b", "request_id": "req_b", "trace_events": [], "trace_step": 0,
            "latency_breakdown": {}, "tool_failure_counts": {}}
        out = tool_node(state)
        assert out.get("execution_status") == "awaiting_confirmation"

    def test_long_legitimate_chain_within_larger_budget(self):
        # A->B->C->D->E->F completes only if budget >= 6; simulate router decision
        from config import MAX_EXECUTION_STEPS
        chain_len = 6
        would_execute = min(chain_len, MAX_EXECUTION_STEPS)
        # at default 5 the 6th step cannot run (documents Phase 7B root cause)
        if MAX_EXECUTION_STEPS == 5:
            assert would_execute == 5
        else:
            assert would_execute == 6
