"""
Unit tests for Phase 3B Planner Reliability & Completion Guards
"""

import pytest
from nodes.planner_node import check_completion_guard, is_repeated_tool_call, PlannerDecision


class TestPlannerReliability:
    def test_calculation_guard_rejects_missing_calculator(self):
        # Query requires calculation but calculator was never called
        question = "Find the population of Japan and calculate 0.5% of it."
        completed_steps = ["web_search"]
        tool_results = [{"tool": "web_search", "arguments": {"query": "Japan population"}, "result": "125 million"}]
        context = ""

        is_complete, reason = check_completion_guard(question, completed_steps, tool_results, context)
        assert is_complete is False
        assert "calculator" in reason.lower()

    def test_calculation_guard_allows_completed_calculator(self):
        question = "Find the population of Japan and calculate 0.5% of it."
        completed_steps = ["web_search", "calculator"]
        tool_results = [
            {"tool": "web_search", "arguments": {"query": "Japan population"}, "result": "125 million"},
            {"tool": "calculator", "arguments": {"expression": "125000000 * 0.005"}, "result": "625000"}
        ]
        context = ""

        is_complete, reason = check_completion_guard(question, completed_steps, tool_results, context)
        assert is_complete is True
        assert reason == ""

    def test_rag_without_calc_guard_allows_final(self):
        # Pure RAG query without requested math should allow final
        question = "According to the company policy document, what is our remote work policy?"
        completed_steps = ["rag"]
        tool_results = []
        context = "Remote work policy: Employees may work from home up to 2 days per week."

        is_complete, reason = check_completion_guard(question, completed_steps, tool_results, context)
        assert is_complete is True
        assert reason == ""

    def test_rag_with_calc_guard_rejects_final_until_calc_called(self):
        # RAG query that explicitly asks for arithmetic
        question = "According to our company policy, how many PTO days do we get per year? If I take 5 days off, how many will I have left?"
        completed_steps = ["rag"]
        tool_results = []
        context = "Employees receive 20 PTO days per year."

        is_complete, reason = check_completion_guard(question, completed_steps, tool_results, context)
        assert is_complete is False
        assert "calculator" in reason.lower()

    def test_repeated_tool_call_detection(self):
        tool_results = [
            {"tool": "web_search", "arguments": {"query": "India population"}, "result": "1.4 billion"}
        ]
        # Same tool and same args -> repeated call loop
        assert is_repeated_tool_call("web_search", {"query": "India population"}, tool_results) is True
        # Different query -> not a loop
        assert is_repeated_tool_call("web_search", {"query": "China population"}, tool_results) is False
        # Different tool -> not a loop
        assert is_repeated_tool_call("calculator", {"expression": "1+1"}, tool_results) is False

    def test_pydantic_planner_decision_schema(self):
        decision = PlannerDecision(
            action="tool",
            tool="calculator",
            arguments={"expression": "100 / 4"}
        )
        assert decision.action == "tool"
        assert decision.tool == "calculator"
        assert decision.arguments == {"expression": "100 / 4"}
