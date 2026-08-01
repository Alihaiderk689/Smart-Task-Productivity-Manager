from django.apps import AppConfig


class CopilotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'copilot'

    def ready(self):
        # Registers every built-in tool onto the shared tool_registry at
        # startup -- agents look tools up by name, so this has to happen
        # exactly once before any agent runs.
        from .tools.action_tools import ProposeActionTool
        from .tools.analytics_tools import GetCategoryBreakdownTool, GetProductivityTrendsTool, GetTaskStatsTool
        from .tools.database_tools import (
            FindDuplicateCategoriesTool,
            GetCopilotActivityStatsTool,
            GetDatabaseStatsTool,
        )
        from .tools.registry import tool_registry
        from .tools.reminder_tools import ListReminderCandidatesTool, SendReminderTool
        from .tools.system_tools import CheckCeleryWorkersTool, CheckDatabaseTool, CheckRedisTool
        from .tools.task_tools import (
            DeleteCompletedTasksTool,
            GetTaskCompletionByCategoryTool,
            ListOverdueTasksTool,
            ListStalePendingTasksTool,
        )
        from .tools.user_tools import DeactivateUserTool, GetUserGrowthStatsTool, ListInactiveUsersTool

        for tool_cls in (
            CheckDatabaseTool,
            CheckRedisTool,
            CheckCeleryWorkersTool,
            GetTaskStatsTool,
            GetProductivityTrendsTool,
            GetCategoryBreakdownTool,
            ListInactiveUsersTool,
            GetUserGrowthStatsTool,
            DeactivateUserTool,
            ListOverdueTasksTool,
            ListStalePendingTasksTool,
            GetTaskCompletionByCategoryTool,
            DeleteCompletedTasksTool,
            ListReminderCandidatesTool,
            SendReminderTool,
            GetDatabaseStatsTool,
            FindDuplicateCategoriesTool,
            GetCopilotActivityStatsTool,
            ProposeActionTool,
        ):
            tool_registry.register(tool_cls())
