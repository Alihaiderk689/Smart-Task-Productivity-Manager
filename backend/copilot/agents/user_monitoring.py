"""Tracks user growth and inactivity. Proposes deactivating long-dormant,
zero-activity accounts as an approval-gated action -- never deactivates
anyone itself (see agents/action.py for the agent that actually executes
an approved proposal)."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent

_DORMANT_DAYS = 90
_MAX_PROPOSALS_PER_RUN = 5


class UserMonitoringAgent(BaseAgent):
    name = "user_monitoring"
    description = "Tracks user growth and inactivity; proposes deactivating long-dormant, zero-activity accounts for admin approval."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()

    def observe(self) -> dict:
        return {}

    def reason(self, observation: dict) -> str:
        return "Checking user growth trends and looking for long-dormant, zero-activity accounts."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [
            PlannedStep(tool_name="get_user_growth_stats", tool_input={"days": 14}, reason="Signup trend."),
            PlannedStep(tool_name="list_inactive_users", tool_input={"days": _DORMANT_DAYS}, reason="Long-dormant accounts."),
        ]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        findings = {step.tool_name: result.data for step, result in tool_results}
        inactive = (findings.get("list_inactive_users") or {}).get("inactive_users", [])
        dormant_zero_activity = [u for u in inactive if u["task_count"] == 0][:_MAX_PROPOSALS_PER_RUN]

        proposed = 0
        for u in dormant_zero_activity:
            if self.recommendations.has_pending_action(tool="deactivate_user", input_match={"user_id": u["id"]}):
                continue
            self.recommendations.create(
                title=f"Deactivate dormant account: {u['email']}",
                description=f"{u['email']} hasn't logged in for {_DORMANT_DAYS}+ days (or never has) and has created zero tasks.",
                reasoning="Long-dormant, zero-activity accounts are candidates for deactivation to keep the user base accurate.",
                impact="The user would no longer be able to log in until reactivated by an admin.",
                risk="medium",
                category="users",
                confidence=0.75,
                action_payload={"tool": "deactivate_user", "input": {"user_id": u["id"]}},
                related_agent_run=agent_run,
            )
            proposed += 1

        summary = f"{len(inactive)} user(s) inactive {_DORMANT_DAYS}+ days; proposed {proposed} for deactivation."
        if self.llm.is_configured:
            try:
                summary = self.llm.summarize(
                    "Summarize this user-activity check for a non-technical admin in 2-3 short sentences. "
                    f"Data: {findings}",
                    system="You are a concise user-engagement analyst for a small task-manager app.",
                )
            except Exception:
                pass
        return summary
