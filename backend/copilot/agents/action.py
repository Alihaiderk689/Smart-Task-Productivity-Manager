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
from ..tools.registry import tool_registry
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

    def _authorization_error(self, rec) -> str | None:
        """Re-validates a Recommendation right at execution time -- the one
        chokepoint every path converges on (chat's immediate-execute,
        the manual /approve/ endpoint, and the Celery sweep for stragglers
        approved-but-not-yet-run). The LLM/proposer's say-so was never the
        authorization mechanism (see SECURITY.md's admin-copilot section);
        this is the actual server-side check: is this still a real,
        sensitive, registered tool, and is the admin who approved it still
        someone with the authority to run it right now -- not just at the
        moment they clicked approve. Catches e.g. a staff account
        deactivated between approval and a delayed sweep execution."""
        tool_name = rec.action_payload.get("tool")
        if tool_name not in tool_registry or not tool_registry.get(tool_name).is_sensitive:
            return f"{tool_name!r} is not a valid sensitive action -- refusing to execute."

        approver = rec.resolved_by
        if approver is None or not approver.is_active or not approver.is_staff:
            return "Approving admin is no longer an active staff account -- action not executed."

        return None

    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        steps = []
        authorized = []
        for rec in self._pending:
            error = self._authorization_error(rec)
            if error:
                self.recommendations.mark_failed(rec, error=error)
                continue

            # Server-injected, never LLM/proposer-controlled (same pattern
            # as action_tools.py's `_requested_by`) -- lets a tool that
            # accepts it (e.g. DeactivateUserTool, DeleteUserTool) refuse to
            # target the acting admin's own account, matching adminpanel's
            # existing self-target guard on the same operations.
            tool_input = dict(rec.action_payload.get("input", {}))
            tool_input["_acting_user_id"] = rec.resolved_by_id

            steps.append(PlannedStep(tool_name=rec.action_payload["tool"], tool_input=tool_input, reason=rec.title))
            authorized.append(rec)

        self._pending = authorized
        return steps

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
