"""Plan schema — generic, service-agnostic structured plan."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    id: str = Field(description="Unique step id, e.g. 's1'")
    tool: str = Field(description="Exact tool name from the available tools list")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments matching the tool schema")
    depends_on: list[str] = Field(default_factory=list, description="Step ids whose outputs this step needs")
    purpose: str = Field(default="", description="Why this step exists for the goal")


class Plan(BaseModel):
    goal: str = Field(description="Restated user goal")
    steps: list[PlanStep] = Field(default_factory=list)
    completion_conditions: str = Field(default="", description="How to know the goal is satisfied")


class PlanValidation(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
