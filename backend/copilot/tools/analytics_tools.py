"""Read-only tools backing the Analytics agent -- task completion stats,
productivity trends over time, and where task volume concentrates by
category. All safe (permission=None): they only ever run SELECTs."""

from __future__ import annotations

from django.db.models import Count
from django.utils import timezone

from tasks.models import Task

from .base import BaseTool, ToolResult

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "required": []}


class GetTaskStatsTool(BaseTool):
    name = "get_task_stats"
    description = "Returns overall task counts by status and the completion rate across every user."
    input_schema = _EMPTY_SCHEMA

    def run(self, **kwargs) -> ToolResult:
        by_status = dict(Task.objects.values_list("status").annotate(count=Count("id")).order_by())
        total = sum(by_status.values())
        completed = by_status.get("Completed", 0)
        rate = round(completed / total * 100, 1) if total else 0.0
        return ToolResult(success=True, data={"total": total, "by_status": by_status, "completion_rate_pct": rate})


class GetProductivityTrendsTool(BaseTool):
    name = "get_productivity_trends"
    description = "Returns the number of tasks completed per calendar day over the last N days (default 14)."
    input_schema = {
        "type": "object",
        "properties": {"days": {"type": "integer", "description": "How many days back, default 14."}},
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        days = int(kwargs.get("days") or 14)
        since = timezone.now() - timezone.timedelta(days=days)
        counts: dict[str, int] = {}
        for completed_at in Task.objects.filter(status="Completed", completed_at__gte=since).values_list(
            "completed_at", flat=True
        ):
            day = timezone.localtime(completed_at).date().isoformat()
            counts[day] = counts.get(day, 0) + 1
        return ToolResult(success=True, data={"days": days, "completions_by_day": counts})


class GetCategoryBreakdownTool(BaseTool):
    name = "get_category_breakdown"
    description = "Returns task counts grouped by category name across all users."
    input_schema = _EMPTY_SCHEMA

    def run(self, **kwargs) -> ToolResult:
        rows = Task.objects.values("category__name").annotate(count=Count("id")).order_by("-count")
        data = {(row["category__name"] or "Uncategorized"): row["count"] for row in rows}
        return ToolResult(success=True, data={"by_category": data})
