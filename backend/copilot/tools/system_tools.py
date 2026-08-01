"""Read-only infrastructure tools -- thin wrappers around core.system_checks
so each check can be called (and logged) individually by an agent's plan,
rather than only as the one combined get_system_status() snapshot that
adminpanel's /system-status/ endpoint uses."""

from __future__ import annotations

from core.system_checks import check_celery_workers, check_database, check_redis

from .base import BaseTool, ToolResult

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "required": []}


class CheckDatabaseTool(BaseTool):
    name = "check_database"
    description = "Checks whether the application database is reachable."
    input_schema = _EMPTY_SCHEMA
    output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    def run(self, **kwargs) -> ToolResult:
        ok = check_database()
        return ToolResult(success=ok, data={"ok": ok}, error="" if ok else "Database is not reachable.")


class CheckRedisTool(BaseTool):
    name = "check_redis"
    description = "Checks whether Redis (the Celery message broker) is reachable."
    input_schema = _EMPTY_SCHEMA
    output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    def run(self, **kwargs) -> ToolResult:
        ok = check_redis()
        return ToolResult(success=ok, data={"ok": ok}, error="" if ok else "Redis is not reachable.")


class CheckCeleryWorkersTool(BaseTool):
    name = "check_celery_workers"
    description = "Checks whether at least one Celery worker is online and responding to a ping."
    input_schema = _EMPTY_SCHEMA
    output_schema = {"type": "object", "properties": {"workers": {"type": "array", "items": {"type": "string"}}}}

    def run(self, **kwargs) -> ToolResult:
        workers = check_celery_workers()
        ok = len(workers) > 0
        return ToolResult(success=ok, data={"workers": workers}, error="" if ok else "No Celery workers responded.")
