"""Audits row counts and simple data-hygiene issues (e.g. duplicate
categories) across the database. Observation-only -- raises a low-risk
alert when hygiene issues are found, proposes no direct fixes since a
duplicate-category cleanup would need per-row judgment a human should make."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent


class DatabaseIntelligenceAgent(BaseAgent):
    name = "database_intelligence"
    description = "Audits row counts and data-hygiene issues (e.g. duplicate categories) across the database."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()

    def observe(self) -> dict:
        return {}

    def reason(self, observation: dict) -> str:
        return "Checking table sizes and looking for data-hygiene issues like duplicate categories."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [
            PlannedStep(tool_name="get_database_stats", reason="Row counts for main tables."),
            PlannedStep(tool_name="find_duplicate_categories", reason="Per-user duplicate category names."),
        ]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        findings = {step.tool_name: result.data for step, result in tool_results}
        stats = findings.get("get_database_stats") or {}
        dup_count = (findings.get("find_duplicate_categories") or {}).get("count", 0)

        summary = (
            f"{stats.get('users', 0)} users, {stats.get('tasks', 0)} tasks, {stats.get('categories', 0)} categories. "
            f"{dup_count} duplicate categor{'y' if dup_count == 1 else 'ies'} found."
        )

        if dup_count > 0 and not self.recommendations.has_recent_pending(
            title="Duplicate categories found", category="database"
        ):
            self.recommendations.create(
                title="Duplicate categories found",
                description=f"{dup_count} user(s) have more than one category with the same name (case-insensitive).",
                reasoning="Duplicate category names can confuse filtering and reporting, even though they don't break anything.",
                impact="Minor -- a data-hygiene issue, not user-facing breakage.",
                risk="low",
                category="database",
                confidence=0.9,
                related_agent_run=agent_run,
            )

        if self.llm.is_configured:
            try:
                summary = self.llm.summarize(
                    "Summarize this database-health check for a non-technical admin in 2-3 short sentences. "
                    f"Data: {findings}",
                    system="You are a concise database-hygiene assistant for a small task-manager app.",
                )
            except Exception:
                pass
        return summary
