"""Data-access layer over the copilot models. Agents and views go through
these rather than the ORM directly, so persistence details (exactly which
fields get set at each stage of a run's lifecycle) live in one place."""

from __future__ import annotations

from django.utils import timezone

from .models import AgentRun, Recommendation, ToolCallLog


class AgentRunRepository:
    def start(self, *, agent_name: str, trigger: str, requested_by=None) -> AgentRun:
        return AgentRun.objects.create(agent_name=agent_name, trigger=trigger, requested_by=requested_by)

    def log_tool_call(self, run: AgentRun, *, tool_name: str, tool_input: dict, result) -> ToolCallLog:
        return ToolCallLog.objects.create(
            agent_run=run,
            tool_name=tool_name,
            input_data=tool_input,
            output_data=result.data,
            success=result.success,
            error=result.error,
        )

    def complete(
        self,
        run: AgentRun,
        *,
        observation_summary: str = "",
        reasoning_summary: str = "",
        plan: list | None = None,
        result_summary: str = "",
        confidence: float | None = None,
    ) -> AgentRun:
        run.status = "completed"
        run.observation_summary = observation_summary
        run.reasoning_summary = reasoning_summary
        run.plan = plan or []
        run.result_summary = result_summary
        run.confidence = confidence
        run.finished_at = timezone.now()
        run.save()
        return run

    def fail(self, run: AgentRun, *, error: str) -> AgentRun:
        run.status = "failed"
        run.error = error
        run.finished_at = timezone.now()
        run.save()
        return run

    def recent(self, *, agent_name: str | None = None, limit: int = 20):
        qs = AgentRun.objects.all()
        if agent_name:
            qs = qs.filter(agent_name=agent_name)
        return qs[:limit]

    def last_for(self, agent_name: str) -> AgentRun | None:
        return AgentRun.objects.filter(agent_name=agent_name).first()


class RecommendationRepository:
    def create(self, **kwargs) -> Recommendation:
        return Recommendation.objects.create(**kwargs)

    def pending(self, *, category: str | None = None):
        qs = Recommendation.objects.filter(status="pending")
        if category:
            qs = qs.filter(category=category)
        return qs

    def recent(self, *, status: str | None = None, limit: int = 50):
        qs = Recommendation.objects.all()
        if status:
            qs = qs.filter(status=status)
        return qs[:limit]

    def approved_pending(self, *, ids: list[int] | None = None):
        """Approved recommendations that haven't been executed yet -- what
        ActionAgent works through on each run."""
        qs = Recommendation.objects.filter(status="approved")
        if ids:
            qs = qs.filter(id__in=ids)
        return qs

    def approve(self, rec: Recommendation, *, by_user) -> Recommendation:
        rec.status = "approved"
        rec.resolved_by = by_user
        rec.resolved_at = timezone.now()
        rec.save(update_fields=["status", "resolved_by", "resolved_at"])
        return rec

    def reject(self, rec: Recommendation, *, by_user) -> Recommendation:
        rec.status = "rejected"
        rec.resolved_by = by_user
        rec.resolved_at = timezone.now()
        rec.save(update_fields=["status", "resolved_by", "resolved_at"])
        return rec

    def mark_executed(self, rec: Recommendation, *, result) -> Recommendation:
        rec.status = "executed"
        rec.execution_result = result if isinstance(result, dict) else {"result": result}
        rec.save(update_fields=["status", "execution_result"])
        return rec

    def mark_failed(self, rec: Recommendation, *, error: str) -> Recommendation:
        rec.status = "failed"
        rec.execution_result = {"error": error}
        rec.save(update_fields=["status", "execution_result"])
        return rec

    def has_pending_action(self, *, tool: str, input_match: dict) -> bool:
        """True if a pending recommendation already proposes this exact
        tool+input -- lets agents avoid re-proposing the same action on
        every scheduled run."""
        qs = Recommendation.objects.filter(status="pending", action_payload__tool=tool)
        for key, value in input_match.items():
            qs = qs.filter(**{f"action_payload__input__{key}": value})
        return qs.exists()

    def has_recent_pending(self, *, title: str, category: str, within_hours: int = 24) -> bool:
        """True if an observation-only alert with this exact title already
        exists and is still pending -- avoids re-raising the same alert on
        every scheduled run."""
        since = timezone.now() - timezone.timedelta(hours=within_hours)
        return Recommendation.objects.filter(
            status="pending", title=title, category=category, created_at__gte=since
        ).exists()
