"""User-scoped task tools -- create/update/delete/complete/reopen/list/
stats/reminders/insights. Every queryset in this file filters on
`self.user` (bound at tool-construction time, see tools/base.py); none of
these tools ever accept a user/user_id argument from the LLM.

Create/update reuse tasks.serializers.TaskSerializer directly rather than
re-implementing its validation -- word/character limits, the gibberish
check, category-ownership scoping, and the start/end-time rules all come
from there for free, and stay in sync with the rest of the app
automatically instead of drifting out of sync with a hand-rolled copy.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from types import SimpleNamespace

from django.db.models import Count, Q
from django.utils import timezone

from notifications.services import NotificationService
from tasks.models import Task
from tasks.serializers import TaskSerializer

from ..services.category_resolver import create_category, list_category_names, resolve_category
from ..services.date_resolver import format_friendly, resolve_datetime
from .base import BaseTool, ToolResult

_STATUS_CHOICES = [c[0] for c in Task.STATUS_CHOICES]
_PRIORITY_CHOICES = [c[0] for c in Task.PRIORITY_CHOICES]


def _fake_request(user):
    """TaskSerializer scopes its `category` field to `context["request"].user`
    -- a real DRF Request isn't available inside a tool, so this minimal
    duck-typed stand-in is all `__init__` actually reads from it."""
    return SimpleNamespace(user=user)


def _first_error(errors) -> str:
    """Flattens a DRF ValidationError.detail-style nested error structure
    into one friendly, user-safe sentence."""
    if isinstance(errors, list) and errors:
        return str(errors[0])
    if isinstance(errors, dict):
        for messages in errors.values():
            result = _first_error(messages)
            if result:
                return result
    return "That doesn't look valid -- please check the details and try again."


def _serialize_brief(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "category": task.category.name,
        "start_time": format_friendly(task.start_time),
        "end_time": format_friendly(task.end_time),
    }


def resolve_task(user, task_id=None, title_query=None) -> tuple[Task | None, str]:
    """Shared task lookup for update/delete/complete/reopen -- by id when
    known (e.g. from an earlier list_tasks result in this conversation),
    otherwise by a case-insensitive substring match on title. Always
    scoped to `user`; never touches another user's tasks."""
    if task_id:
        task = Task.objects.filter(user=user, id=task_id).first()
        if not task:
            return None, f"I couldn't find a task with id {task_id}."
        return task, ""

    title_query = (title_query or "").strip()
    if not title_query:
        return None, "Which task do you mean? Tell me its title (or part of it)."

    matches = list(Task.objects.filter(user=user, title__icontains=title_query).order_by("-created_at")[:6])
    if not matches:
        return None, f"I couldn't find a task matching \"{title_query}\"."
    if len(matches) > 1:
        listed = "; ".join(f"\"{t.title}\" ({t.status}, due {format_friendly(t.end_time)})" for t in matches)
        return None, f"I found more than one task matching \"{title_query}\": {listed}. Which one did you mean?"
    return matches[0], ""


class CreateTaskTool(BaseTool):
    name = "create_task"
    description = (
        "Creates a new task for the current user. Requires a title, category, start time, and "
        "end time -- if any of these aren't known yet from the conversation, ask the user for "
        "them instead of calling this tool with a guess."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short task title (max 20 words)."},
            "description": {"type": "string", "description": "Optional longer description (max 200 words)."},
            "category_name": {"type": "string", "description": "One of the user's existing category names, or a new one to create (only once they've confirmed)."},
            "create_category_if_missing": {"type": "boolean", "description": "Set true only after the user has explicitly said yes to creating this new category."},
            "priority": {"type": "string", "enum": _PRIORITY_CHOICES, "description": "Defaults to Medium if not mentioned."},
            "start_time": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-08-15T15:00:00."},
            "end_time": {"type": "string", "description": "ISO 8601 datetime, must be after start_time."},
        },
        "required": ["title", "category_name", "start_time", "end_time"],
    }

    def run(self, **kwargs) -> ToolResult:
        category_name = (kwargs.get("category_name") or "").strip()
        if not category_name:
            return ToolResult(success=False, error="I need a category for this task.")

        category = resolve_category(self.user, category_name)
        if category is None:
            if not kwargs.get("create_category_if_missing"):
                return ToolResult(success=True, data={
                    "status": "needs_category_confirmation",
                    "message": f"I couldn't find a category called \"{category_name}\". Want me to create it?",
                    "category_name": category_name,
                })
            category = create_category(self.user, category_name)

        start_dt, start_err = resolve_datetime(kwargs.get("start_time"))
        if start_err:
            return ToolResult(success=False, error=start_err)
        end_dt, end_err = resolve_datetime(kwargs.get("end_time"))
        if end_err:
            return ToolResult(success=False, error=end_err)

        payload = {
            "title": (kwargs.get("title") or "").strip(),
            "description": (kwargs.get("description") or "").strip(),
            "category": category.id,
            "priority": kwargs.get("priority") or "Medium",
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
        }
        serializer = TaskSerializer(data=payload, context={"request": _fake_request(self.user)})
        if not serializer.is_valid():
            return ToolResult(success=False, error=_first_error(serializer.errors))

        task = serializer.save(user=self.user)
        NotificationService.schedule_reminders(task)

        return ToolResult(success=True, data={**_serialize_brief(task), "status_note": "created, reminders scheduled"})


class UpdateTaskTool(BaseTool):
    name = "update_task"
    description = (
        "Changes one or more fields of an existing task the user already has -- title, "
        "description, category, priority, start time, or end time. Identify the task by "
        "task_id (if known from earlier in the conversation) or title_query (a few words from "
        "its current title). Only include the new_* fields that are actually changing."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer"},
            "title_query": {"type": "string", "description": "Words from the task's current title, if its id isn't known."},
            "new_title": {"type": "string"},
            "new_description": {"type": "string"},
            "new_category_name": {"type": "string"},
            "new_priority": {"type": "string", "enum": _PRIORITY_CHOICES},
            "new_start_time": {"type": "string", "description": "ISO 8601 datetime."},
            "new_end_time": {"type": "string", "description": "ISO 8601 datetime."},
        },
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        task, err = resolve_task(self.user, kwargs.get("task_id"), kwargs.get("title_query"))
        if err:
            return ToolResult(success=False, error=err)

        payload = {}
        if kwargs.get("new_title"):
            payload["title"] = kwargs["new_title"].strip()
        if kwargs.get("new_description") is not None:
            payload["description"] = kwargs["new_description"].strip()
        if kwargs.get("new_priority"):
            payload["priority"] = kwargs["new_priority"]

        if kwargs.get("new_category_name"):
            category_name = kwargs["new_category_name"].strip()
            category = resolve_category(self.user, category_name)
            if category is None:
                if not kwargs.get("create_category_if_missing"):
                    return ToolResult(success=True, data={
                        "status": "needs_category_confirmation",
                        "message": f"I couldn't find a category called \"{category_name}\". Want me to create it?",
                        "category_name": category_name,
                    })
                category = create_category(self.user, category_name)
            payload["category"] = category.id

        if kwargs.get("new_start_time"):
            start_dt, start_err = resolve_datetime(kwargs["new_start_time"])
            if start_err:
                return ToolResult(success=False, error=start_err)
            payload["start_time"] = start_dt.isoformat()
        if kwargs.get("new_end_time"):
            end_dt, end_err = resolve_datetime(kwargs["new_end_time"])
            if end_err:
                return ToolResult(success=False, error=end_err)
            payload["end_time"] = end_dt.isoformat()

        if not payload:
            return ToolResult(success=False, error="What would you like to change about this task?")

        serializer = TaskSerializer(task, data=payload, partial=True, context={"request": _fake_request(self.user)})
        if not serializer.is_valid():
            return ToolResult(success=False, error=_first_error(serializer.errors))
        task = serializer.save()

        return ToolResult(success=True, data={**_serialize_brief(task), "status_note": "updated"})


class DeleteTaskTool(BaseTool):
    name = "delete_task"
    description = (
        "Permanently deletes one of the user's tasks. NEVER call this with confirmed=true in "
        "the same turn the user first mentions deleting something -- first ask them to confirm "
        "in plain text, and only pass confirmed=true after they've explicitly said yes in a "
        "later message. Identify the task by task_id or title_query."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer"},
            "title_query": {"type": "string", "description": "Words from the task's title, if its id isn't known."},
            "confirmed": {"type": "boolean", "description": "Must be true -- only after the user has explicitly confirmed deleting this specific task."},
        },
        "required": ["confirmed"],
    }

    def run(self, **kwargs) -> ToolResult:
        task, err = resolve_task(self.user, kwargs.get("task_id"), kwargs.get("title_query"))
        if err:
            return ToolResult(success=False, error=err)

        if not kwargs.get("confirmed"):
            return ToolResult(success=True, data={
                "status": "needs_confirmation",
                "message": f"Are you sure you want to delete \"{task.title}\"? This can't be undone.",
                "task_id": task.id,
            })

        title = task.title
        task.delete()
        return ToolResult(success=True, data={"status": "deleted", "title": title})


class CompleteTaskTool(BaseTool):
    name = "complete_task"
    description = "Marks one of the user's tasks as completed. Works regardless of its current status (Pending, In Progress, Paused)."
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer"},
            "title_query": {"type": "string", "description": "Words from the task's title, if its id isn't known."},
        },
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        task, err = resolve_task(self.user, kwargs.get("task_id"), kwargs.get("title_query"))
        if err:
            return ToolResult(success=False, error=err)

        if task.status == "Completed":
            return ToolResult(success=True, data={"status": "already_completed", "title": task.title})

        now = timezone.now()
        if not task.started_at:
            task.started_at = now
        task.completed_at = now
        task.status = "Completed"
        task.save(update_fields=["status", "started_at", "completed_at"])
        return ToolResult(success=True, data={**_serialize_brief(task), "status_note": "marked complete"})


class ReopenTaskTool(BaseTool):
    name = "reopen_task"
    description = "Undoes a task's completion, setting it back to Pending. Only works on tasks that are currently Completed."
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer"},
            "title_query": {"type": "string", "description": "Words from the task's title, if its id isn't known."},
        },
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        task, err = resolve_task(self.user, kwargs.get("task_id"), kwargs.get("title_query"))
        if err:
            return ToolResult(success=False, error=err)

        if task.status != "Completed":
            return ToolResult(success=False, error=f"\"{task.title}\" isn't marked complete right now (it's {task.status}), so there's nothing to reopen.")

        task.status = "Pending"
        task.completed_at = None
        task.started_at = None
        task.save(update_fields=["status", "completed_at", "started_at"])
        return ToolResult(success=True, data={**_serialize_brief(task), "status_note": "reopened"})


class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = (
        "Lists/searches the user's own tasks with optional filters -- covers both browsing "
        "(\"what's due today\", \"show overdue tasks\") and searching (\"find my React tasks\", "
        "\"show completed gym tasks\"). Combine filters freely."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "when": {"type": "string", "enum": ["today", "tomorrow", "this_week", "upcoming", "overdue", "any"], "description": "Date-range shortcut, default any."},
            "status": {"type": "string", "enum": _STATUS_CHOICES},
            "category_name": {"type": "string"},
            "priority": {"type": "string", "enum": _PRIORITY_CHOICES},
            "keyword": {"type": "string", "description": "Free-text search against title and description."},
            "limit": {"type": "integer", "description": "Max results, default 20, capped at 50."},
        },
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        qs = Task.objects.filter(user=self.user)
        now = timezone.now()
        today = timezone.localdate()

        when = kwargs.get("when") or "any"
        if when == "today":
            qs = qs.filter(start_time__date=today)
        elif when == "tomorrow":
            qs = qs.filter(start_time__date=today + timedelta(days=1))
        elif when == "this_week":
            end_of_week = today + timedelta(days=(6 - today.weekday()))
            qs = qs.filter(start_time__date__gte=today, start_time__date__lte=end_of_week)
        elif when == "upcoming":
            qs = qs.filter(start_time__gt=now)
        elif when == "overdue":
            qs = qs.filter(end_time__lt=now).exclude(status__in=["Completed", "Stopped"])

        if kwargs.get("status"):
            qs = qs.filter(status=kwargs["status"])
        if kwargs.get("priority"):
            qs = qs.filter(priority=kwargs["priority"])

        if kwargs.get("category_name"):
            category = resolve_category(self.user, kwargs["category_name"])
            if category is None:
                return ToolResult(success=True, data={"count": 0, "tasks": [], "note": f"No category matching \"{kwargs['category_name']}\"."})
            qs = qs.filter(category=category)

        if kwargs.get("keyword"):
            keyword = kwargs["keyword"]
            qs = qs.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))

        limit = min(int(kwargs.get("limit") or 20), 50)
        tasks = list(qs.select_related("category").order_by("start_time")[:limit])
        return ToolResult(success=True, data={"count": len(tasks), "tasks": [_serialize_brief(t) for t in tasks]})


class GetTaskStatsTool(BaseTool):
    name = "get_task_stats"
    description = "Overall task statistics for the user: counts by status, completion rate, overdue count, most-used category."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> ToolResult:
        qs = Task.objects.filter(user=self.user)
        by_status = dict(qs.values_list("status").annotate(count=Count("id")).order_by())
        total = sum(by_status.values())
        completed = by_status.get("Completed", 0)
        rate = round(completed / total * 100, 1) if total else 0.0
        overdue = qs.filter(end_time__lt=timezone.now()).exclude(status__in=["Completed", "Stopped"]).count()
        top_category = qs.values("category__name").annotate(count=Count("id")).order_by("-count").first()

        return ToolResult(success=True, data={
            "total_tasks": total,
            "by_status": by_status,
            "completion_rate_pct": rate,
            "overdue_count": overdue,
            "pending_count": by_status.get("Pending", 0),
            "most_used_category": top_category["category__name"] if top_category else None,
        })


class GetRemindersTool(BaseTool):
    name = "get_reminders"
    description = (
        "Answers questions about upcoming reminders -- derived from each active task's start/end "
        "time (30-min-before, 5-min-before, and due-at-end reminders), same as what actually gets "
        "emailed. 'next' returns just the single soonest one; 'today' returns all of today's."
    )
    input_schema = {
        "type": "object",
        "properties": {"when": {"type": "string", "enum": ["next", "today"], "description": "Defaults to 'next'."}},
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        when = kwargs.get("when") or "next"
        now = timezone.now()
        today = timezone.localdate()
        active = Task.objects.filter(user=self.user).exclude(status__in=["Completed", "Stopped", "Missed"])

        reminders = []
        for task in active:
            for label, at in (
                ("starts in 30 minutes", task.start_time - timedelta(minutes=30)),
                ("starts in 5 minutes", task.start_time - timedelta(minutes=5)),
                ("is due", task.end_time),
            ):
                if at > now:
                    reminders.append({"task": task.title, "type": label, "at": at})
        reminders.sort(key=lambda r: r["at"])

        def fmt(r):
            return {"task": r["task"], "type": r["type"], "at": format_friendly(r["at"])}

        if when == "today":
            todays = [r for r in reminders if timezone.localtime(r["at"]).date() == today]
            return ToolResult(success=True, data={"count": len(todays), "reminders": [fmt(r) for r in todays]})

        if not reminders:
            return ToolResult(success=True, data={"reminders": [], "message": "No upcoming reminders."})
        return ToolResult(success=True, data={"reminders": [fmt(reminders[0])]})


class GetProductivityInsightsTool(BaseTool):
    name = "get_productivity_insights"
    description = (
        "Productivity insights for the user: category breakdown by task count, which day of the "
        "week they complete the most tasks, tasks completed this week, and their current daily "
        "completion streak."
    )
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> ToolResult:
        qs = Task.objects.filter(user=self.user)
        completed = qs.filter(status="Completed", completed_at__isnull=False)

        category_breakdown = [
            {"category": row["category__name"], "count": row["count"]}
            for row in qs.values("category__name").annotate(count=Count("id")).order_by("-count")
        ]

        by_weekday = Counter(
            timezone.localtime(dt).strftime("%A") for dt in completed.values_list("completed_at", flat=True)
        )
        busiest_day = max(by_weekday.items(), key=lambda kv: kv[1])[0] if by_weekday else None

        week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        completed_this_week = completed.filter(completed_at__date__gte=week_start).count()

        streak = self._current_streak(completed)

        return ToolResult(success=True, data={
            "category_breakdown": category_breakdown,
            "busiest_day": busiest_day,
            "completed_this_week": completed_this_week,
            "current_streak_days": streak,
        })

    @staticmethod
    def _current_streak(completed_qs) -> int:
        # No streak field exists anywhere in this app -- computed fresh each
        # call from completed_at dates (consecutive days walking back from
        # today), not persisted.
        done_dates = {timezone.localtime(dt).date() for dt in completed_qs.values_list("completed_at", flat=True)}
        streak = 0
        cursor = timezone.localdate()
        while cursor in done_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak


class ListCategoriesTool(BaseTool):
    name = "list_categories"
    description = "Lists the user's existing category names -- useful before creating/updating a task to check what categories already exist."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"categories": list_category_names(self.user)})
