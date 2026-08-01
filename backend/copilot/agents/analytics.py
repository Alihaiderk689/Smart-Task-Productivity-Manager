"""Analyzes task completion trends and category breakdowns -- surfaces
productivity insights. Observation-only most of the time; raises a single
alert when the overall completion rate looks concerning."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent

_LOW_COMPLETION_THRESHOLD_PCT = 30
_MIN_TASKS_FOR_SIGNAL = 5


class AnalyticsAgent(BaseAgent):
    name = "analytics"
    description = "Analyzes task completion trends and category breakdowns; surfaces productivity insights."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()

    def observe(self) -> dict:
        return {}

    def reason(self, observation: dict) -> str:
        return "Gathering task statistics, completion trends, and category breakdown."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [
            PlannedStep(tool_name="get_task_stats", reason="Overall completion rate."),
            PlannedStep(tool_name="get_productivity_trends", tool_input={"days": 14}, reason="14-day completion trend."),
            PlannedStep(tool_name="get_category_breakdown", reason="Where task volume concentrates."),
        ]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        findings = {step.tool_name: result.data for step, result in tool_results}
        stats = findings.get("get_task_stats", {}) or {}
        total = stats.get("total", 0)
        rate = stats.get("completion_rate_pct", 0)

        summary = f"Completion rate: {rate}% across {total} tasks."

        if (
            total >= _MIN_TASKS_FOR_SIGNAL
            and rate < _LOW_COMPLETION_THRESHOLD_PCT
            and not self.recommendations.has_recent_pending(title="Low overall task completion rate", category="tasks")
        ):
            self.recommendations.create(
                title="Low overall task completion rate",
                description=f"Only {rate}% of {total} tasks have been completed.",
                reasoning="A completion rate below 30% across a meaningful sample suggests users are overcommitting or losing track of tasks.",
                impact="Users may be disengaging from the app if tasks pile up uncompleted.",
                risk="medium",
                category="tasks",
                confidence=0.7,
                related_agent_run=agent_run,
            )

        if self.llm.is_configured:
            try:
                summary = self.llm.summarize(
                    "Summarize these task analytics for a non-technical admin in 2-3 short sentences, "
                    f"highlighting anything notable. Data: {findings}",
                    system="You are a concise productivity-analytics assistant for a small task-manager app.",
                )
            except Exception:
                pass
        return summary
