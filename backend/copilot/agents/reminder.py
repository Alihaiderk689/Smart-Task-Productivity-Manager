"""Finds tasks whose reminder window has arrived (or passed) without the
flag being marked sent, and proposes sending it. Deliberately
approval-gated like every other data-changing agent, even though the
underlying send_reminder tool has its own idempotency guard -- an admin
should still see and approve any email the copilot causes to go out."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from ..tools.base import PlannedStep, ToolResult
from .base import BaseAgent

_MAX_PROPOSALS_PER_RUN = 5


class ReminderAgent(BaseAgent):
    name = "reminder"
    description = "Finds tasks whose reminder likely got missed and proposes sending it, for admin approval."

    def __init__(self, *, recommendations: RecommendationRepository | None = None, **kwargs):
        super().__init__(**kwargs)
        self.recommendations = recommendations or RecommendationRepository()

    def observe(self) -> dict:
        return {}

    def reason(self, observation: dict) -> str:
        return "Looking for tasks due soon or overdue whose reminder hasn't been marked sent yet."

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        return [PlannedStep(tool_name="list_reminder_candidates", reason="Tasks that may have missed a reminder.")]

    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        return all(result.success for _, result in tool_results)

    def report(self, *, agent_run, observation, reasoning, plan, tool_results, verified) -> str:
        _, result = tool_results[0]
        candidates = (result.data or {}).get("candidates", []) if result.success else []

        proposed = 0
        for c in candidates[:_MAX_PROPOSALS_PER_RUN]:
            reminder_type = "overdue" if c["kind"] == "overdue" else "30min"
            if self.recommendations.has_pending_action(tool="send_reminder", input_match={"task_id": c["id"]}):
                continue
            self.recommendations.create(
                title=f"Send missed reminder: {c['title']}",
                description=f"Task {c['title']!r} (owner: {c['owner_email']}) appears to have missed its {reminder_type} reminder.",
                reasoning="The reminder window passed (or is imminent) without the corresponding flag being marked sent.",
                impact="The task owner may not be aware their task is due or overdue.",
                risk="low",
                category="reminders",
                confidence=0.7,
                action_payload={"tool": "send_reminder", "input": {"task_id": c["id"], "reminder_type": reminder_type}},
                related_agent_run=agent_run,
            )
            proposed += 1

        summary = f"{len(candidates)} task(s) may need a reminder; proposed {proposed} for approval."
        if self.llm.is_configured:
            try:
                summary = self.llm.summarize(
                    f"Summarize this reminder check for a non-technical admin in 1-2 short sentences. "
                    f"Found {len(candidates)} candidate(s), proposed {proposed} for approval.",
                    system="You are a concise reminders-monitoring assistant for a small task-manager app.",
                )
            except Exception:
                pass
        return summary
