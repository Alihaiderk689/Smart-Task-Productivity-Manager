"""A process-wide registry of tool instances. Agents look tools up by name
(so a plan produced by an LLM, which only knows tool names as strings, can
be executed) instead of importing each tool module directly."""

from __future__ import annotations

from .base import BaseTool


class ToolNotFoundError(KeyError):
    pass


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> BaseTool:
        if not tool.name:
            raise ValueError(f"{tool.__class__.__name__} must set a non-empty `name`")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"No tool registered as {name!r}") from None

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def as_llm_schema(self) -> list[dict]:
        """Every registered tool's definition, ready to pass as `tools=` to
        GroqClient.chat()."""
        return [tool.to_llm_schema() for tool in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


# A single shared registry for the whole app -- agents import this rather
# than constructing their own, so every agent sees every registered tool.
tool_registry = ToolRegistry()
