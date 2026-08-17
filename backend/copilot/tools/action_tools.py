"""propose_action -- the one tool the chat orchestrator uses to run a
data-changing action on behalf of the admin it's currently talking to.
Always logs a Recommendation row first (so every sensitive action has the
same audit trail agents' own proposals get -- title, reasoning, category,
risk, action_payload, who/when, execution result), then immediately
approves and executes it via ActionAgent, since the only caller of this
tool is ChatService (see services/chat_service.py::_run_tool), which only
ever runs behind the IsAdminUser-gated /admin/copilot chat endpoint --
by the time an admin's message reaches this tool, a human admin has
already given the order in the moment, so a second, separate manual
approval click would just be re-confirming the same request. Autonomous
agents (UserMonitoringAgent, etc.) never call this tool -- they write
Recommendation rows directly via RecommendationRepository.create() for
system-initiated suggestions nobody explicitly asked for, which still go
through the normal manual approve/reject endpoints in views.py."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from .base import BaseTool, ToolResult
from .registry import tool_registry

_CATEGORY_CHOICES = ["users", "tasks", "reminders", "system", "database"]
_RISK_CHOICES = ["low", "medium", "high"]


class ProposeActionTool(BaseTool):
    name = "propose_action"
    description = (
        "Runs an action that changes data (e.g. deactivating a user, sending a reminder) on the admin's "
        "behalf -- logged as a Recommendation for audit purposes and executed immediately, since you're "
        "already talking to an admin who just asked for this. For a genuinely destructive, irreversible "
        "action (delete_user, delete_completed_tasks), get an explicit yes from the admin in chat first; "
        "for lower-risk actions (deactivate_user, rename_user, send_reminder) you may call this directly. "
        "Always use this instead of claiming to have made a change yourself."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title for the action."},
            "description": {"type": "string", "description": "What this action does and why."},
            "tool": {
                "type": "string",
                "description": "Name of the sensitive tool to run, e.g. 'deactivate_user' or 'send_reminder'.",
            },
            "tool_input": {"type": "object", "description": "The arguments to pass to that tool."},
            "category": {"type": "string", "enum": _CATEGORY_CHOICES},
            "risk": {"type": "string", "enum": _RISK_CHOICES, "description": "Defaults to 'medium' if omitted."},
        },
        "required": ["title", "description", "tool", "tool_input", "category"],
    }
    permission = None  # safe -- the tool itself only ever runs behind admin-gated chat; see module docstring

    def __init__(self, *, recommendations: RecommendationRepository | None = None):
        self.recommendations = recommendations or RecommendationRepository()

    def run(self, **kwargs) -> ToolResult:
        title = (kwargs.get("title") or "").strip()
        target_tool = kwargs.get("tool")
        tool_input = kwargs.get("tool_input") or {}
        category = kwargs.get("category") or "system"
        risk = kwargs.get("risk") or "medium"
        # Injected by ChatService, never by the LLM (not part of input_schema) --
        # the admin currently chatting, on whose behalf this action runs.
        requested_by = kwargs.get("_requested_by")

        if not title or not target_tool:
            return ToolResult(success=False, error="'title' and 'tool' are required.")
        if target_tool not in tool_registry:
            return ToolResult(success=False, error=f"Unknown tool {target_tool!r} -- cannot propose an action for a tool that doesn't exist.")
        if category not in _CATEGORY_CHOICES:
            category = "system"
        if risk not in _RISK_CHOICES:
            risk = "medium"

        rec = self.recommendations.create(
            title=title,
            description=kwargs.get("description", ""),
            reasoning="Requested via Admin Copilot chat.",
            risk=risk,
            category=category,
            confidence=0.7,
            action_payload={"tool": target_tool, "input": tool_input},
        )

        if requested_by is None:
            # No admin identity to execute on behalf of (e.g. called outside
            # a live chat request) -- fall back to the old propose-only
            # behavior rather than auto-executing on nobody's authority.
            return ToolResult(
                success=True,
                data={"recommendation_id": rec.id, "title": rec.title, "status": rec.status, "requires_approval": True},
            )

        from ..agents.action import ActionAgent  # local import: avoids a module-load cycle with agents/action.py

        self.recommendations.approve(rec, by_user=requested_by)
        ActionAgent(recommendations=self.recommendations, only_ids=[rec.id]).run(trigger="chat", requested_by=requested_by)
        rec.refresh_from_db()

        return ToolResult(
            success=rec.status == "executed",
            data={
                "recommendation_id": rec.id,
                "title": rec.title,
                "status": rec.status,
                "requires_approval": False,
                "execution_result": rec.execution_result,
            },
            error="" if rec.status == "executed" else str((rec.execution_result or {}).get("error", "Execution failed.")),
        )
