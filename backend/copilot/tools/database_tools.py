"""Read-only tools backing the Database Intelligence agent -- row counts
and simple data-hygiene checks. All safe (permission=None)."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Count
from django.db.models.functions import Lower

from categories.models import Category
from tasks.models import Task

from ..models import AgentRun, Recommendation
from .base import BaseTool, ToolResult

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "required": []}


class GetDatabaseStatsTool(BaseTool):
    name = "get_database_stats"
    description = "Returns row counts for the main application tables (users, tasks, categories, agent runs, recommendations)."
    input_schema = _EMPTY_SCHEMA

    def run(self, **kwargs) -> ToolResult:
        data = {
            "users": User.objects.count(),
            "tasks": Task.objects.count(),
            "categories": Category.objects.count(),
            "agent_runs": AgentRun.objects.count(),
            "recommendations": Recommendation.objects.count(),
        }
        return ToolResult(success=True, data=data)


class FindDuplicateCategoriesTool(BaseTool):
    name = "find_duplicate_categories"
    description = (
        "Finds users who have more than one category with the same name (case-insensitive) -- "
        "a data-hygiene check, since this is normally prevented for exact matches by a unique constraint."
    )
    input_schema = _EMPTY_SCHEMA

    def run(self, **kwargs) -> ToolResult:
        rows = (
            Category.objects.annotate(lname=Lower("name"))
            .values("user_id", "lname")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        data = [{"user_id": r["user_id"], "name": r["lname"], "count": r["count"]} for r in rows]
        return ToolResult(success=True, data={"duplicates": data, "count": len(data)})


class GetCopilotActivityStatsTool(BaseTool):
    name = "get_copilot_activity_stats"
    description = "Returns how many agent runs and recommendations exist by status -- for auditing the copilot's own footprint."
    input_schema = _EMPTY_SCHEMA

    def run(self, **kwargs) -> ToolResult:
        by_status = dict(AgentRun.objects.values_list("status").annotate(count=Count("id")).order_by())
        rec_by_status = dict(Recommendation.objects.values_list("status").annotate(count=Count("id")).order_by())
        return ToolResult(success=True, data={"agent_runs_by_status": by_status, "recommendations_by_status": rec_by_status})
