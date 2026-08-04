from django.apps import AppConfig


class UsercopilotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'usercopilot'

    def ready(self):
        # Registers every built-in user-copilot tool onto the shared
        # tool_registry at startup -- see tools/registry.py.
        from .tools.registry import tool_registry
        from .tools.task_tools import (
            CompleteTaskTool,
            CreateTaskTool,
            DeleteTaskTool,
            GetProductivityInsightsTool,
            GetRemindersTool,
            GetTaskStatsTool,
            ListCategoriesTool,
            ListTasksTool,
            ReopenTaskTool,
            UpdateTaskTool,
        )

        for tool_cls in (
            CreateTaskTool,
            UpdateTaskTool,
            DeleteTaskTool,
            CompleteTaskTool,
            ReopenTaskTool,
            ListTasksTool,
            GetTaskStatsTool,
            GetRemindersTool,
            GetProductivityInsightsTool,
            ListCategoriesTool,
        ):
            tool_registry.register(tool_cls)
