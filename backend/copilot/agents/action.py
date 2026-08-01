"""Executes admin-approved actions -- and only admin-approved actions. Its
plan() is built entirely from Recommendation.action_payload rows that are
already status="approved" (see repositories.RecommendationRepository), so
this agent never decides *what* to do on its own; a human already decided
that when they approved the recommendation. Runs two ways: scoped to a
single recommendation right after an admin clicks Approve (see
views.approve_recommendation), and as a periodic sweep (Celery Beat) that
catches anything approved but, for whatever reason, not yet executed."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent


class ActionAgent(BaseAgent):
    name = "action"
    description = "Executes admin-approved actions (deactivating dormant users, sending missed reminders, etc.) exactly as approved."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, only_ids: list[int] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()
        self.only_ids = only_ids
        self._pending: list = []

    def observe(self) -> dict:
        self._pending = list(self.recommendations.approved_pending(ids=self.only_ids))
        return {"approved_count": len(self._pending)}

    def reason(self, observation: dict) -> str:
        n = observation["approved_count"]
        return f"Found {n} approved action(s) waiting to execute." if n else "No approved actions waiting to execute."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [
            PlannedStep(
                tool_name=rec.action_payload["tool"],
                tool_input=rec.action_payload.get("input", {}),
                reason=rec.title,
            )
            for rec in self._pending
        ]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        lines = []
        for rec, (_step, result) in zip(self._pending, tool_results):
            if result.success:
                self.recommendations.mark_executed(rec, result=result.data)
                lines.append(f"Executed: {rec.title}")
            else:
                self.recommendations.mark_failed(rec, error=result.error)
                lines.append(f"Failed: {rec.title} ({result.error})")

        return "\n".join(lines) if lines else "No approved actions to execute."
