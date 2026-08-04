"""The tool abstraction the User Copilot is built from. Deliberately
separate from copilot/tools/base.py (the admin copilot's tool base) even
though the shape looks similar -- these two tool families must never be
mixed into one registry (see tools/registry.py), because that's exactly
the kind of accident that would let a user-facing tool slip into an
admin-only context or vice versa.

SECURITY: every tool here is instantiated per-request bound to the
authenticated user (see ready-made pattern in ToolRegistry.for_user()) --
`user` is a constructor argument, never a field in `input_schema`. The LLM
supplies tool call arguments as freeform JSON; if "user" or "user_id" were
among those fields, a hallucinated (or adversarially prompted) tool call
could ask for another user's id. Binding `self.user` server-side, before
the LLM ever sees the tool, makes that class of bug structurally
impossible rather than something every tool author has to remember.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """What every tool.run() returns, success or failure -- never an
    exception. `data` is whatever JSON-serializable payload the LLM needs
    to see to answer the user; `error` is a short, user-safe message (never
    a stack trace or raw exception text)."""

    success: bool
    data: Any = None
    error: str = ""

    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data, "error": self.error}


class BaseTool(ABC):
    """Subclass this, set name/description/input_schema, implement run().
    `self.user` is always the authenticated Django User this tool instance
    is bound to -- every queryset inside run() must filter on it."""

    name: str = ""
    description: str = ""
    input_schema: dict = {"type": "object", "properties": {}, "required": []}

    def __init__(self, *, user):
        self.user = user

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        """Execute the tool for self.user. Must not raise -- catch and
        return ToolResult(success=False, error=...) instead. `error` must
        never leak an internal exception message, SQL, or stack trace."""
        raise NotImplementedError

    def to_llm_schema(self) -> dict:
        """Groq/OpenAI-compatible function-calling tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def __repr__(self):
        return f"<UserTool {self.name!r} user={getattr(self.user, 'id', None)!r}>"
