"""A process-wide registry of user-copilot TOOL CLASSES (not instances --
contrast with copilot/tools/registry.py, which registers singleton
instances since admin tools don't need per-request binding). Each chat
request calls `tool_registry.for_user(request.user)` to get a fresh set of
tool instances bound to that one user; nothing here is ever shared across
requests, so there's no possibility of one user's bound tool instance
leaking into another user's request."""

from __future__ import annotations

from .base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tool_classes: dict[str, type[BaseTool]] = {}

    def register(self, tool_cls: type[BaseTool]) -> type[BaseTool]:
        if not tool_cls.name:
            raise ValueError(f"{tool_cls.__name__} must set a non-empty `name`")
        self._tool_classes[tool_cls.name] = tool_cls
        return tool_cls

    def names(self) -> list[str]:
        return list(self._tool_classes.keys())

    def schemas(self) -> list[dict]:
        """Groq/OpenAI-compatible function-calling schemas for every
        registered tool -- safe to build without a user, since name/
        description/input_schema are all class-level."""
        return [
            {
                "type": "function",
                "function": {
                    "name": cls.name,
                    "description": cls.description,
                    "parameters": cls.input_schema,
                },
            }
            for cls in self._tool_classes.values()
        ]

    def for_user(self, user) -> dict[str, BaseTool]:
        """Fresh, user-bound instances of every registered tool -- call
        once per chat request, never cache/reuse across requests."""
        return {name: cls(user=user) for name, cls in self._tool_classes.items()}

    def __contains__(self, name: str) -> bool:
        return name in self._tool_classes

    def __len__(self) -> int:
        return len(self._tool_classes)


# A single shared registry of tool *classes* for the whole app.
tool_registry = ToolRegistry()
