"""Tracks overdue and stalled tasks across all users. Observation-only --
raises an alert when the overdue count looks concerning, but proposes no
actions of its own (see agents/reminder.py for the agent that proposes
actually nudging owners)."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent

_HIGH_OVERDUE_THRESHOLD = 10


class TaskIntelligenceAgent(BaseAgent):
    name = "task_intelligence"
    description = "Tracks overdue and stalled tasks across all users and flags concerning patterns."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()

    def observe(self) -> dict:
        return {}

    def reason(self, observation: dict) -> str:
        return "Checking for overdue tasks, stalled pending tasks, and completion rates by category."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [
            PlannedStep(tool_name="list_overdue_tasks", tool_input={"limit": 10}, reason="Currently overdue tasks."),
            PlannedStep(tool_name="list_stale_pending_tasks", tool_input={"hours": 24, "limit": 10}, reason="Tasks never started."),
            PlannedStep(tool_name="get_task_completion_by_category", reason="Completion rate by category."),
        ]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        findings = {step.tool_name: result.data for step, result in tool_results}
        total_overdue = (findings.get("list_overdue_tasks") or {}).get("total_overdue", 0)
        stale_count = (findings.get("list_stale_pending_tasks") or {}).get("count", 0)

        summary = f"{total_overdue} task(s) overdue, {stale_count} task(s) never started despite a past start time."

        if total_overdue >= _HIGH_OVERDUE_THRESHOLD and not self.recommendations.has_recent_pending(
            title="High number of overdue tasks", category="tasks"
        ):
            self.recommendations.create(
                title="High number of overdue tasks",
                description=f"There are currently {total_overdue} overdue tasks across all users.",
                reasoning="A high overdue count suggests reminders aren't landing or users are overcommitted.",
                impact="Users may be missing deadlines without realizing it.",
                risk="medium",
                category="tasks",
                confidence=0.8,
                related_agent_run=agent_run,
            )

        if self.llm.is_configured:
            try:
                summary = self.llm.summarize(
                    "Summarize this task-health check for a non-technical admin in 2-3 short sentences. "
                    f"Data: {findings}",
                    system="You are a concise task-management analyst for a small task-manager app.",
                )
            except Exception:
                pass
        return summary
