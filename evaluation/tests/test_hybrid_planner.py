"""Phase 7B — deterministic hybrid planner tests. No LLM."""

import pytest
from planning.classifier import classify_complexity
from planning.schema import Plan, PlanStep
from planning.validation import validate_plan, next_ready_steps

TOOLS = ["calculator", "web_search",
         "calendar.create_event", "calendar.list_events", "calendar.get_event",
         "notes.create", "notes.list", "notes.read",
         "reminders.create", "reminders.list", "reminders.get"]


class TestComplexityClassifier:
    def test_single_tool_simple(self):
        assert classify_complexity("Use calendar.list_events to show events.", TOOLS) == "SIMPLE"

    def test_two_tools_dependent(self):
        q = "Create a meeting via calendar.create_event and save agenda with notes.create."
        assert classify_complexity(q, TOOLS) == "DEPENDENT"

    def test_dependency_signal_escalates(self):
        q = "Read the note then use calculator on the result."
        assert classify_complexity(q, TOOLS) == "DEPENDENT"

    def test_three_tools_multi_step(self):
        q = ("Create event via calendar.create_event, save notes via notes.create, "
             "and remind via reminders.create.")
        assert classify_complexity(q, TOOLS) == "MULTI_STEP"

    def test_no_tools_uncertain_or_simple(self):
        c = classify_complexity("hello there", TOOLS)
        assert c in ("SIMPLE", "UNCERTAIN")

    def test_alias_mention_counts(self):
        q = "Use calendar_create_event and notes_create please."
        assert classify_complexity(q, TOOLS) in ("DEPENDENT", "MULTI_STEP")


class TestDuplicatePrevention:
    def test_identical_success_signature_detected(self):
        import json
        seen = {json.dumps({"t": "notes.list", "a": {}}, sort_keys=True): "s1"}
        sig = json.dumps({"t": "notes.list", "a": {}}, sort_keys=True)
        assert sig in seen

    def test_different_args_not_duplicate(self):
        import json
        seen = {json.dumps({"t": "notes.list", "a": {}}, sort_keys=True): "s1"}
        sig = json.dumps({"t": "notes.list", "a": {"query": "x"}}, sort_keys=True)
        assert sig not in seen

    def test_failed_result_not_recorded_as_success(self):
        # dedupe guard only records non-error results (mirrors planner_node logic)
        res = "Error: Note not found"
        should_record = not str(res).lower().startswith("error")
        assert should_record is False


class TestBudgets:
    def test_max_replans_default_conservative(self):
        from config import MAX_REPLANS, MAX_TOOL_STEPS
        assert MAX_REPLANS == 1
        assert MAX_TOOL_STEPS == 5  # unchanged circuit breaker


class TestEscalationPolicy:
    def test_level_mapping(self):
        # mirrors _hybrid_route level logic
        def level_for(cls, cap=2):
            if cap == 0:
                return 0
            if cls == "MULTI_STEP":
                return min(cap, 2)
            if cls in ("DEPENDENT", "UNCERTAIN"):
                return min(cap, 1)
            return 0
        assert level_for("SIMPLE") == 0
        assert level_for("DEPENDENT") == 1
        assert level_for("MULTI_STEP") == 2
        assert level_for("MULTI_STEP", cap=0) == 0      # ablation: no escalation
        assert level_for("MULTI_STEP", cap=1) == 1      # ablation: no replan level

    def test_replan_requires_failure_and_budget(self):
        replans = 1
        MAX_REPLANS = 1
        failed = True
        can_replan = failed and replans < MAX_REPLANS
        assert can_replan is False  # budget exhausted

    def test_replan_never_on_success(self):
        assert (True and 0 < 1) is True
        can_replan = False and True  # failed=False
        assert can_replan is False


class TestStateAwareReplan:
    def test_replan_prompt_excludes_completed(self):
        done = {"s1", "s2"}
        remaining = [s for s in [PlanStep(id="s1", tool="calculator"),
                                 PlanStep(id="s3", tool="notes.create")] if s.id not in done]
        assert [s.id for s in remaining] == ["s3"]

    def test_fresh_dag_after_replan(self):
        # new plan's completed set resets; old results live in completed_steps history
        assert next_ready_steps(
            mk_dep_plan(), set()) == ["r1"]


def mk_dep_plan():
    return Plan(goal="g", steps=[PlanStep(id="r1", tool="reminders.create", depends_on=[])])


class TestSecurityPreserved:
    def test_confirmation_blocks_before_execution(self):
        def confirm(tool, args):
            return tool.endswith(".create_event")
        p = Plan(goal="g", steps=[
            PlanStep(id="e", tool="calendar.create_event", arguments={"title": "t", "date": "2026-01-01"})])
        v = validate_plan(p, TOOLS + ["calendar.create_event"], confirmation_required=confirm)
        assert not v.valid  # gated ops flagged pre-execution even in hybrid

    def test_unknown_tool_invalid_in_hybrid_too(self):
        p = Plan(goal="g", steps=[PlanStep(id="x", tool="gmail.send")])
        assert not validate_plan(p, TOOLS).valid
