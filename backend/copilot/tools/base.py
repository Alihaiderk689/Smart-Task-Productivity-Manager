"""The tool abstraction every agent capability is built from. A tool is a
single, narrowly-scoped callable (check Redis, query overdue tasks, send an
email...) with a declared input/output shape and a permission tier -- the
same shape an LLM tool-calling API (Groq/OpenAI-style) expects, so a tool
defined here can be handed straight to GroqClient.chat(tools=...) as well as
called directly by deterministic agent code.
"""

# The venv here is Python 3.9 -- `str | None` union syntax needs 3.10+
# without this (PEP 604 vs. PEP 563 deferred evaluation).
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """What every tool.run() returns, success or failure -- callers should
    never need to catch an exception from a well-behaved tool; failures are
    represented in-band so agents can decide how to react."""

    success: bool
    data: Any = None
    error: str = ""

    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data, "error": self.error}


@dataclass
class PlannedStep:
    """One entry in an agent's plan -- which tool, with what input, and why
    (the "why" is what gets shown to an admin in an approval prompt, and
    what gets logged for the "thought process" trail)."""

    tool_name: str
    tool_input: dict = field(default_factory=dict)
    reason: str = ""


class BaseTool(ABC):
    """Subclass this, set the four class attributes, implement run(). See
    copilot/tools/system_tools.py for a reference implementation."""

    name: str = ""
    description: str = ""
    # JSON Schema (the "parameters" object of an LLM function/tool
    # definition) -- e.g. {"type": "object", "properties": {...}, "required": [...]}
    input_schema: dict = {"type": "object", "properties": {}, "required": []}
    output_schema: dict = {"type": "object"}

    # None = anyone with copilot access can invoke it without approval.
    # "sensitive" = mutates data; an agent must route this through a
    # Recommendation + admin approval rather than calling it directly.
    permission: str | None = None

    @property
    def is_sensitive(self) -> bool:
        return self.permission == "sensitive"

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        """Execute the tool. Must not raise -- catch and return
        ToolResult(success=False, error=...) instead, so agent code never
        needs a try/except around a tool call."""
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
        return f"<Tool {self.name!r} permission={self.permission!r}>"
