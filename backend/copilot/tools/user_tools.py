"""Tools backing the User Monitoring agent -- read-only inactivity/growth
checks, plus one sensitive mutation (deactivate_user) that must only ever
be invoked as an admin-approved action (see agents/action.py), never called
directly from an agent's own plan()."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone

from .base import BaseTool, ToolResult

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "required": []}


class ListInactiveUsersTool(BaseTool):
    name = "list_inactive_users"
    description = (
        "Lists active, non-staff users who haven't logged in for at least N days (default 30), "
        "or have never logged in at all, along with their task count."
    )
    input_schema = {
        "type": "object",
        "properties": {"days": {"type": "integer", "description": "Inactivity threshold in days, default 30."}},
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        days = int(kwargs.get("days") or 30)
        cutoff = timezone.now() - timezone.timedelta(days=days)
        qs = (
            User.objects.filter(is_staff=False, is_active=True)
            .filter(Q(last_login__lt=cutoff) | Q(last_login__isnull=True))
            .annotate(task_count=Count("tasks"))
            .order_by("last_login")[:50]
        )
        data = [
            {
                "id": u.id,
                "email": u.email,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "task_count": u.task_count,
            }
            for u in qs
        ]
        return ToolResult(success=True, data={"days": days, "inactive_users": data, "count": len(data)})


class GetUserGrowthStatsTool(BaseTool):
    name = "get_user_growth_stats"
    description = "Returns new-user signup counts per calendar day over the last N days (default 14)."
    input_schema = {
        "type": "object",
        "properties": {"days": {"type": "integer", "description": "How many days back, default 14."}},
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        days = int(kwargs.get("days") or 14)
        since = timezone.now() - timezone.timedelta(days=days)
        counts: dict[str, int] = {}
        for joined in User.objects.filter(date_joined__gte=since).values_list("date_joined", flat=True):
            day = timezone.localtime(joined).date().isoformat()
            counts[day] = counts.get(day, 0) + 1
        return ToolResult(success=True, data={"days": days, "signups_by_day": counts})


class DeactivateUserTool(BaseTool):
    name = "deactivate_user"
    description = "Deactivates a user account, preventing them from logging in. Only run after explicit admin approval."
    input_schema = {
        "type": "object",
        "properties": {"user_id": {"type": "integer", "description": "The id of the user to deactivate."}},
        "required": ["user_id"],
    }
    permission = "sensitive"

    def run(self, **kwargs) -> ToolResult:
        user_id = kwargs.get("user_id")
        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return ToolResult(success=False, error=f"No user with id {user_id!r}.")

        if user.is_superuser:
            return ToolResult(success=False, error="Superuser accounts cannot be deactivated here.")
        if not user.is_active:
            return ToolResult(success=True, data={"user_id": user.id, "email": user.email, "is_active": False})

        user.is_active = False
        user.save(update_fields=["is_active"])
        return ToolResult(success=True, data={"user_id": user.id, "email": user.email, "is_active": False})
