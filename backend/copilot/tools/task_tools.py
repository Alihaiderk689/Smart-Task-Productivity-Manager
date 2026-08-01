"""Read-only tools backing the Task Intelligence agent -- overdue tasks,
tasks that were never started, and per-category completion rates."""

from __future__ import annotations

from django.db.models import Count, Q
from django.utils import timezone

from tasks.models import Task

from .base import BaseTool, ToolResult

_INACTIVE_STATUSES = ["Completed", "Stopped"]


class ListOverdueTasksTool(BaseTool):
    name = "list_overdue_tasks"
    description = "Lists tasks whose end_time has passed but that aren't Completed or Stopped."
    input_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Max rows to return, default 20."}},
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        limit = int(kwargs.get("limit") or 20)
        base_qs = Task.objects.filter(end_time__lt=timezone.now()).exclude(status__in=_INACTIVE_STATUSES)
        rows = base_qs.select_related("user").order_by("end_time")[:limit]
        data = [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "owner_email": t.user.email,
                "end_time": t.end_time.isoformat(),
            }
            for t in rows
        ]
        return ToolResult(success=True, data={"overdue_tasks": data, "total_overdue": base_qs.count()})


class ListStalePendingTasksTool(BaseTool):
    name = "list_stale_pending_tasks"
    description = "Lists tasks still 'Pending' whose start_time was more than N hours ago (default 24) -- i.e. never started."
    input_schema = {
        "type": "object",
        "properties": {
            "hours": {"type": "integer", "description": "How many hours past start_time counts as stale, default 24."},
            "limit": {"type": "integer", "description": "Max rows to return, default 20."},
        },
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        hours = int(kwargs.get("hours") or 24)
        limit = int(kwargs.get("limit") or 20)
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        qs = Task.objects.filter(status="Pending", start_time__lt=cutoff).select_related("user").order_by("start_time")
        rows = qs[:limit]
        data = [
            {"id": t.id, "title": t.title, "owner_email": t.user.email, "start_time": t.start_time.isoformat()}
            for t in rows
        ]
        return ToolResult(success=True, data={"stale_tasks": data, "count": qs.count(), "hours": hours})


class DeleteCompletedTasksTool(BaseTool):
    name = "delete_completed_tasks"
    description = (
        "Permanently deletes tasks that are 'Completed' and were completed more than N days ago "
        "(default 30) -- bulk cleanup of old completed tasks. Only run after explicit admin approval."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "older_than_days": {"type": "integer", "description": "Delete only tasks completed more than this many days ago, default 30."},
            "user_id": {"type": "integer", "description": "Optional -- limit to one user's tasks instead of all users."},
        },
        "required": [],
    }
    permission = "sensitive"

    def run(self, **kwargs) -> ToolResult:
        older_than_days = int(kwargs.get("older_than_days") or 30)
        cutoff = timezone.now() - timezone.timedelta(days=older_than_days)
        qs = Task.objects.filter(status="Completed", completed_at__lt=cutoff)

        user_id = kwargs.get("user_id")
        if user_id is not None:
            qs = qs.filter(user_id=user_id)

        deleted_ids = list(qs.values_list("id", flat=True))
        if deleted_ids:
            qs.delete()

        return ToolResult(
            success=True,
            data={"deleted_count": len(deleted_ids), "deleted_task_ids": deleted_ids, "older_than_days": older_than_days},
        )


class GetTaskCompletionByCategoryTool(BaseTool):
    name = "get_task_completion_by_category"
    description = "Returns total and completed task counts, plus completion rate, per category name across all users."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> ToolResult:
        rows = Task.objects.values("category__name").annotate(
            total=Count("id"), completed=Count("id", filter=Q(status="Completed"))
        ).order_by("-total")

        data = {}
        for row in rows:
            name = row["category__name"] or "Uncategorized"
            total = row["total"]
            rate = round(row["completed"] / total * 100, 1) if total else 0.0
            data[name] = {"total": total, "completed": row["completed"], "completion_rate_pct": rate}
        return ToolResult(success=True, data={"by_category": data})
