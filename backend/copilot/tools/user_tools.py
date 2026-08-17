"""Tools backing the User Monitoring agent -- read-only inactivity/growth/
listing checks, plus sensitive mutations (deactivate_user, delete_user,
rename_user) that must only ever be invoked as an admin-approved action
(see agents/action.py), never called directly from an agent's own plan()
or from Admin Copilot chat (see chat_service.py::_run_tool)."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers

from users.validators import validate_full_name

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


class ListAllUsersTool(BaseTool):
    name = "list_all_users"
    description = (
        "Lists user accounts on the platform -- active or inactive, staff or not -- with their "
        "id, name, email, status, and join date. 'username' in the result is always identical to "
        "'email' (this app has no separate username field); 'name' is the editable display name "
        "that rename_user changes. Use this to look up a user's id before proposing delete_user or "
        "rename_user via propose_action."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["all", "active", "inactive"], "description": "Filter by account status, default 'all'."},
            "keyword": {"type": "string", "description": "Case-insensitive search against name and email."},
            "limit": {"type": "integer", "description": "Max results, default 100, capped at 500."},
        },
        "required": [],
    }

    def run(self, **kwargs) -> ToolResult:
        qs = User.objects.all()

        status = kwargs.get("status") or "all"
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)

        keyword = (kwargs.get("keyword") or "").strip()
        if keyword:
            qs = qs.filter(Q(first_name__icontains=keyword) | Q(email__icontains=keyword) | Q(username__icontains=keyword))

        limit = min(int(kwargs.get("limit") or 100), 500)
        qs = qs.order_by("-date_joined")[:limit]

        data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "name": u.first_name,
                "is_active": u.is_active,
                "is_staff": u.is_staff,
                "date_joined": u.date_joined.isoformat(),
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in qs
        ]
        return ToolResult(success=True, data={"count": len(data), "users": data})


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


class DeleteUserTool(BaseTool):
    name = "delete_user"
    description = (
        "Permanently deletes a user account and everything tied to it (tasks, categories, "
        "copilot chat history) -- this cannot be undone. Only run after explicit admin approval."
    )
    input_schema = {
        "type": "object",
        "properties": {"user_id": {"type": "integer", "description": "The id of the user to delete."}},
        "required": ["user_id"],
    }
    permission = "sensitive"

    def run(self, **kwargs) -> ToolResult:
        user_id = kwargs.get("user_id")
        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return ToolResult(success=False, error=f"No user with id {user_id!r}.")

        if user.is_staff or user.is_superuser:
            return ToolResult(success=False, error="Staff/superuser accounts cannot be deleted here -- use the Django admin site for that.")

        email = user.email
        user.delete()
        return ToolResult(success=True, data={"user_id": user_id, "email": email, "deleted": True})


class RenameUserTool(BaseTool):
    name = "rename_user"
    description = (
        "Changes a user's name. This app has no separate editable username field -- a user's "
        "'username' is always the same as their email and can't be changed, so when an admin asks "
        "to rename, change the username, or change the display name for a user, this is the "
        "correct (and only) action; use it rather than refusing. Only run after explicit admin "
        "approval."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "integer", "description": "The id of the user to rename."},
            "new_name": {"type": "string", "description": "The user's new full name."},
        },
        "required": ["user_id", "new_name"],
    }
    permission = "sensitive"

    def run(self, **kwargs) -> ToolResult:
        user_id = kwargs.get("user_id")
        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return ToolResult(success=False, error=f"No user with id {user_id!r}.")

        try:
            new_name = validate_full_name(kwargs.get("new_name"))
        except serializers.ValidationError as exc:
            return ToolResult(success=False, error=str(exc.detail[0]))

        old_name = user.first_name
        user.first_name = new_name
        user.save(update_fields=["first_name"])
        return ToolResult(success=True, data={"user_id": user.id, "email": user.email, "old_name": old_name, "new_name": user.first_name})
