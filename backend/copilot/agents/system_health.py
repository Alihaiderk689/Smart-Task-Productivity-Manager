"""The first concrete agent -- monitors Redis, Celery workers, and the
database, and raises a Recommendation (an alert; nothing to approve, it's
observation-only) when something's unreachable. No destructive actions,
which makes it a safe reference implementation of the Observe -> Report
loop before the approval-gated agents (Action Agent and friends) exist.
"""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent


class SystemHealthAgent(BaseAgent):
    name = "system_health"
    description = "Monitors Redis, Celery workers, and the database; alerts when something is unreachable."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()

    def observe(self) -> dict:
        # Nothing to gather up front -- the plan below IS the observation
        # (three read-only pings), and each one gets logged as a normal
        # tool call regardless.
        return {}

    def reason(self, observation: dict) -> str:
        return "Checking database, Redis, and Celery worker connectivity."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [
            PlannedStep(tool_name="check_database", reason="Confirm the database is reachable."),
            PlannedStep(tool_name="check_redis", reason="Confirm the Celery broker is reachable."),
            PlannedStep(tool_name="check_celery_workers", reason="Confirm at least one worker is online."),
        ]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        findings = {step.tool_name: result.data for step, result in tool_results}
        problems = [step.tool_name for step, result in tool_results if not result.success]

        if not problems:
            summary = "All systems operational: database, Redis, and Celery workers are all reachable."
        else:
            readable = ", ".join(p.replace("check_", "").replace("_", " ") for p in problems)
            summary = f"Issues detected: {readable}. An alert has been raised."
            if not self.recommendations.has_recent_pending(title="System health issue detected", category="system"):
                self.recommendations.create(
                    title="System health issue detected",
                    description=f"The following checks failed: {readable}.",
                    reasoning="Automated system health check found one or more infrastructure components unreachable.",
                    impact="Users may see failed logins, missed reminders, or a broken app until this is resolved.",
                    risk="high",
                    category="system",
                    confidence=1.0,
                    related_agent_run=agent_run,
                )

        if self.llm.is_configured:
            try:
                summary = self.llm.summarize(
                    f"Summarize this infrastructure health check for a non-technical admin, in 2-3 short "
                    f"sentences. Findings: {findings}",
                    system="You are a concise infrastructure monitoring assistant for a small task-manager app.",
                )
            except Exception:
                pass  # keep the deterministic summary above -- an LLM hiccup must not break reporting

        return summary
