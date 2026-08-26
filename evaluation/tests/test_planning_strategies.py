"""Phase 7 — deterministic plan schema/validation/execution tests. No LLM."""

import pytest
from planning.schema import Plan, PlanStep, PlanValidation
from planning.validation import validate_plan, next_ready_steps, plan_complete, topological_order

VALID = ["calculator", "calendar.create_event", "notes.create", "reminders.create"]


def mk_plan(steps):
    return Plan(goal="test", steps=steps)


class TestPlanSchema:
    def test_valid_schema(self):
        p = mk_plan([PlanStep(id="s1", tool="calculator", arguments={"expression": "1+1"})])
        assert p.steps[0].id == "s1"
        v = validate_plan(p, VALID)
        assert v.valid

    def test_missing_required_field_rejected(self):
        with pytest.raises(Exception):
            PlanStep(id="s1")  # tool required


class TestValidation:
    def test_unknown_tool_rejected(self):
        p = mk_plan([PlanStep(id="s1", tool="gmail.send")])
        v = validate_plan(p, VALID)
        assert not v.valid and any("unknown tool" in e for e in v.errors)

    def test_missing_dependency_rejected(self):
        p = mk_plan([PlanStep(id="s2", tool="notes.create", depends_on=["s1"])])
        v = validate_plan(p, VALID)
        assert not v.valid and any("missing step" in e for e in v.errors)

    def test_circular_dependency_detected(self):
        p = mk_plan([
            PlanStep(id="a", tool="calculator", depends_on=["b"]),
            PlanStep(id="b", tool="calculator", depends_on=["a"]),
        ])
        v = validate_plan(p, VALID)
        assert not v.valid and any("circular" in e for e in v.errors)

    def test_self_dependency_rejected(self):
        p = mk_plan([PlanStep(id="a", tool="calculator", depends_on=["a"])])
        v = validate_plan(p, VALID)
        assert not v.valid

    def test_duplicate_ids_rejected(self):
        p = mk_plan([
            PlanStep(id="s1", tool="calculator"),
            PlanStep(id="s1", tool="notes.create"),
        ])
        v = validate_plan(p, VALID)
        assert not v.valid and any("duplicate" in e for e in v.errors)

    def test_confirmation_flagged(self):
        def confirm(tool, args):
            return tool.endswith("create_event")
        p = mk_plan([
            PlanStep(id="e", tool="calendar.create_event", arguments={"title": "x", "date": "2026-01-01"}),
            PlanStep(id="r", tool="reminders.create", arguments={"text": "y"}),
        ])
        v = validate_plan(p, VALID, confirmation_required=confirm)
        assert not v.valid and any("confirmation" in e for e in v.errors)
        # without hook it's structurally valid
        assert validate_plan(p, VALID).valid

    def test_dependency_ordering_topological(self):
        p = mk_plan([
            PlanStep(id="s3", tool="reminders.create", depends_on=["s1"]),
            PlanStep(id="s1", tool="calendar.create_event"),
            PlanStep(id="s2", tool="notes.create", depends_on=["s1"]),
        ])
        order = topological_order(p)
        assert order.index("s1") < order.index("s2") < order.index("s3")


class TestExecutionHelpers:
    def _plan(self):
        return mk_plan([
            PlanStep(id="s1", tool="calendar.create_event"),
            PlanStep(id="s2", tool="reminders.create", depends_on=["s1"]),
            PlanStep(id="s3", tool="notes.create"),  # independent
        ])

    def test_ready_steps_respect_dependencies(self):
        ready = next_ready_steps(self._plan(), set())
        assert set(ready) == {"s1", "s3"}
        ready2 = next_ready_steps(self._plan(), {"s1"})
        assert set(ready2) == {"s2", "s3"}

    def test_no_infinite_ready(self):
        p = self._plan()
        done = {"s1", "s2", "s3"}
        assert next_ready_steps(p, done) == []
        assert plan_complete(p, done)

    def test_state_propagation_fields(self):
        # simulate: s1 result stored, s2 consumes placeholder
        results = {"s1": '{"event_id": "evt_001"}'}
        args = {"text": "{s1}"}
        for k, v in list(args.items()):
            if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
                ref = v[1:-1]
                if ref in results:
                    args[k] = results[ref]
        assert args["text"] == '{"event_id": "evt_001"}'


class TestReplanState:
    def test_failed_steps_identified(self):
        from nodes.planner_node import check_completion_guard  # import sanity
        tool_results = [
            {"tool": "notes.read", "result": "Error: Note not found: note_999"},
            {"tool": "calculator", "result": "12"},
        ]
        failed = [r for r in tool_results if str(r.get("result", "")).lower().startswith("error")]
        assert len(failed) == 1 and failed[0]["tool"] == "notes.read"
