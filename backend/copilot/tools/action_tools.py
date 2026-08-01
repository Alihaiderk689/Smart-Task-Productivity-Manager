"""propose_action -- the one tool the chat orchestrator (and any agent)
uses to request a data-changing action instead of performing it directly.
Itself completely safe (permission=None): calling it only ever creates a
pending Recommendation row for a human admin to separately approve or
reject via the approval endpoints (see views.py) -- see agents/action.py
for the agent that actually executes an approved one."""

from __future__ import annotations

from ..repositories import RecommendationRepository
from .base import BaseTool, ToolResult
from .registry import tool_registry

_CATEGORY_CHOICES = ["users", "tasks", "reminders", "system", "database"]
_RISK_CHOICES = ["low", "medium", "high"]


class ProposeActionTool(BaseTool):
    name = "propose_action"
    description = (
        "Proposes an action that changes data (e.g. deactivating a user, sending a reminder) for a human "
        "admin to review and approve. This does NOT perform the action -- it only creates a pending "
        "recommendation. Always use this instead of claiming to have made a change yourself."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title for the proposed action."},
            "description": {"type": "string", "description": "What this action would do and why."},
            "tool": {
                "type": "string",
                "description": "Name of the sensitive tool to run if approved, e.g. 'deactivate_user' or 'send_reminder'.",
            },
            "tool_input": {"type": "object", "description": "The arguments to pass to that tool if approved."},
            "category": {"type": "string", "enum": _CATEGORY_CHOICES},
            "risk": {"type": "string", "enum": _RISK_CHOICES, "description": "Defaults to 'medium' if omitted."},
        },
        "required": ["title", "description", "tool", "tool_input", "category"],
    }
    permission = None  # safe -- creates a pending row, executes nothing itself

    def __init__(self, *, recommendations: RecommendationRepository | None = None):
        self.recommendations = recommendations or RecommendationRepository()

    def run(self, **kwargs) -> ToolResult:
        title = (kwargs.get("title") or "").strip()
        target_tool = kwargs.get("tool")
        tool_input = kwargs.get("tool_input") or {}
        category = kwargs.get("category") or "system"
        risk = kwargs.get("risk") or "medium"

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
            reasoning="Proposed via Admin Copilot chat.",
            risk=risk,
            category=category,
            confidence=0.7,
            action_payload={"tool": target_tool, "input": tool_input},
        )
        return ToolResult(
            success=True,
            data={"recommendation_id": rec.id, "title": rec.title, "status": rec.status, "requires_approval": True},
        )
