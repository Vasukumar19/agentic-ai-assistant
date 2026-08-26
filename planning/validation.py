"""Plan validation + dependency-ordered execution helpers. All generic, no service names."""

from __future__ import annotations

from typing import Any

from .schema import Plan, PlanValidation


def validate_plan(plan: Plan, valid_tool_names: list[str], confirmation_required=None) -> PlanValidation:
    """Structural validation — no execution. confirmation_required(tool)->bool optional hook."""
    errors: list[str] = []
    ids = [s.id for s in plan.steps]
    # unique step ids
    if len(ids) != len(set(ids)):
        errors.append("duplicate step ids")
    idset = set(ids)
    for s in plan.steps:
        if s.tool not in valid_tool_names:
            errors.append(f"unknown tool '{s.tool}' in step {s.id}")
        for dep in s.depends_on:
            if dep not in idset:
                errors.append(f"step {s.id} depends on missing step '{dep}'")
            if dep == s.id:
                errors.append(f"step {s.id} depends on itself")
    # circular dependency detection via Kahn's algorithm
    indeg = {sid: 0 for sid in ids}
    adj = {sid: [] for sid in ids}
    for s in plan.steps:
        for dep in s.depends_on:
            if dep in adj and s.id in indeg:
                adj[dep].append(s.id)
                indeg[s.id] += 1
    queue = [sid for sid, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        n = queue.pop()
        seen += 1
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if seen != len(ids):
        errors.append("circular dependency detected")
    # destructive ops must be confirmable
    if confirmation_required:
        for s in plan.steps:
            try:
                if confirmation_required(s.tool, s.arguments):
                    errors.append(f"step {s.id} ({s.tool}) requires confirmation before execution")
            except Exception:
                pass
    return PlanValidation(valid=not errors, errors=errors)


def next_ready_steps(plan: Plan, completed: set[str]) -> list[str]:
    """Step ids whose dependencies are all satisfied and not yet done (topological order)."""
    ready = []
    for s in plan.steps:
        if s.id in completed:
            continue
        if all(d in completed for d in s.depends_on):
            ready.append(s.id)
    return ready


def mark_step_done(completed: set[str], step_id: str) -> set[str]:
    completed.add(step_id)
    return completed


def plan_complete(plan: Plan, completed: set[str]) -> bool:
    return all(s.id in completed for s in plan.steps)


def topological_order(plan: Plan) -> list[str]:
    """Deterministic execution order (Kahn), or [] if cyclic."""
    indeg = {s.id: 0 for s in plan.steps}
    adj = {s.id: [] for s in plan.steps}
    for s in plan.steps:
        for dep in s.depends_on:
            if dep in adj:
                adj[dep].append(s.id)
                indeg[s.id] += 1
    order = []
    queue = sorted([sid for sid, d in indeg.items() if d == 0])
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
                queue.sort()
    return order if len(order) == len(plan.steps) else []
