"""Tools backing the Reminder agent -- a read-only scan for tasks whose
reminder window has arrived (or passed) without the corresponding flag
being set, plus one sensitive tool that actually sends a reminder. Reuses
the same real reminder functions adminpanel's manual "trigger reminder"
button uses (see adminpanel/views.py::trigger_reminder) -- same guards,
same idempotency, just reachable by an agent instead of only a click."""

from __future__ import annotations

from django.utils import timezone

from notifications.tasks import (
    send_5_minute_reminder,
    send_30_minute_reminder,
    send_overdue_reminder,
    send_progress_reminder,
)
from tasks.models import Task

from .base import BaseTool, ToolResult

_INACTIVE_STATUSES = ["Completed", "Stopped"]

REMINDER_FUNCS = {
    "30min": (send_30_minute_reminder, "reminder_30_sent"),
    "5min": (send_5_minute_reminder, "reminder_5_sent"),
    "progress": (send_progress_reminder, "reminder_progress_sent"),
    "overdue": (send_overdue_reminder, "reminder_overdue_sent"),
}


class ListReminderCandidatesTool(BaseTool):
    name = "list_reminder_candidates"
    description = (
        "Lists tasks that likely need a reminder soon: due within 30 minutes, or already overdue, "
        "whose corresponding reminder flag hasn't been marked sent yet."
    )
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> ToolResult:
        now = timezone.now()
        soon = now + timezone.timedelta(minutes=30)
        active = Task.objects.exclude(status__in=_INACTIVE_STATUSES).select_related("user")

        due_soon = active.filter(end_time__gte=now, end_time__lte=soon, reminder_30_sent=False)
        overdue = active.filter(end_time__lt=now, reminder_overdue_sent=False)

        def serialize(qs, kind):
            return [
                {"id": t.id, "title": t.title, "owner_email": t.user.email, "end_time": t.end_time.isoformat(), "kind": kind}
                for t in qs[:20]
            ]

        data = serialize(due_soon, "due_soon") + serialize(overdue, "overdue")
        return ToolResult(success=True, data={"candidates": data, "count": len(data)})


class SendReminderTool(BaseTool):
    name = "send_reminder"
    description = "Sends a specific reminder email for a task right now, if it currently qualifies. Only run after explicit admin approval."
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "The id of the task to send a reminder for."},
            "reminder_type": {"type": "string", "enum": list(REMINDER_FUNCS), "description": "Which reminder to send."},
        },
        "required": ["task_id", "reminder_type"],
    }
    permission = "sensitive"

    def run(self, **kwargs) -> ToolResult:
        task_id = kwargs.get("task_id")
        reminder_type = kwargs.get("reminder_type")
        trigger = REMINDER_FUNCS.get(reminder_type)
        if not trigger:
            return ToolResult(success=False, error=f"reminder_type must be one of {list(REMINDER_FUNCS)}.")

        try:
            task = Task.objects.get(pk=task_id)
        except (Task.DoesNotExist, ValueError, TypeError):
            return ToolResult(success=False, error=f"No task with id {task_id!r}.")

        func, sent_field = trigger
        was_sent_before = getattr(task, sent_field)
        func(task.id, task.reminder_version)
        task.refresh_from_db()
        now_sent = getattr(task, sent_field)

        return ToolResult(
            success=True,
            data={"task_id": task.id, "sent": bool(now_sent and not was_sent_before), "already_sent": was_sent_before},
        )
