"""The meta agent: reviews pending recommendations raised by every other
agent plus a couple of live stats, and writes one prioritized digest. Never
creates recommendations itself -- its whole job is synthesizing what the
other seven agents have already surfaced into "here's what needs your
attention today", ranked by risk."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent

_RISK_RANK = {"high": 0, "medium": 1, "low": 2}
_TOP_N_IN_LLM_PROMPT = 10
_TOP_N_IN_SUMMARY = 5


class RecommendationAgent(BaseAgent):
    name = "recommendation"
    description = "Reviews pending recommendations from every other agent and writes a prioritized digest for the admin."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()

    def observe(self) -> dict:
        return {}

    def reason(self, observation: dict) -> str:
        return "Reviewing all pending recommendations and current system stats to prioritize what needs attention."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [
            PlannedStep(tool_name="get_task_stats", reason="Overall task health."),
            PlannedStep(tool_name="get_database_stats", reason="Overall data volume."),
        ]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        findings = {step.tool_name: result.data for step, result in tool_results}

        pending = list(self.recommendations.pending()[:50])
        pending.sort(key=lambda r: (_RISK_RANK.get(r.risk, 3), -r.created_at.timestamp()))

        if not pending:
            summary = "No pending recommendations right now -- nothing urgent needs your attention."
        else:
            lines = [f"{i + 1}. [{r.risk}] {r.title}" for i, r in enumerate(pending[:_TOP_N_IN_SUMMARY])]
            summary = f"{len(pending)} recommendation(s) awaiting your review:\n" + "\n".join(lines)

        if self.llm.is_configured and pending:
            try:
                digest_input = {
                    "pending_recommendations": [
                        {"title": r.title, "risk": r.risk, "category": r.category} for r in pending[:_TOP_N_IN_LLM_PROMPT]
                    ],
                    "task_stats": findings.get("get_task_stats"),
                    "database_stats": findings.get("get_database_stats"),
                }
                summary = self.llm.summarize(
                    "Write a short prioritized digest (3-5 sentences max) for a busy admin, telling them what "
                    f"most needs their attention today and why. Data: {digest_input}",
                    system="You are a concise chief-of-staff assistant summarizing priorities for a small task-manager app's admin.",
                )
            except Exception:
                pass
        return summary
