"""The planning contract. For agents with a fixed, deterministic checklist
(SystemHealthAgent: always check DB+Redis+Celery) an agent's own plan()
method is the whole planner -- no separate class needed. This module is
for agents whose plan depends on open-ended reasoning over data the LLM
just produced (e.g. a Database Intelligence agent deciding which ORM
query best answers a free-form question): those agents compose a Planner
here instead of hand-writing plan() themselves.

Nothing in the current SystemHealthAgent slice uses this yet -- it's the
seam future agents plug into, kept separate so BaseAgent doesn't have to
change shape when they arrive.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..tools.base import PlannedStep
from ..tools.registry import ToolRegistry


class BasePlanner(ABC):
    """Turns (observation, reasoning) into an ordered list of tool calls."""

    def __init__(self, *, tools: ToolRegistry):
        self.tools = tools

    @abstractmethod
    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        raise NotImplementedError
