"""The Observe -> Reason -> Plan -> Execute -> Verify -> Report loop every
agent implements. Subclasses fill in observe/reason/plan/verify (the parts
that differ per agent); execute/report/run/confidence are shared
orchestration every agent gets for free unless it overrides them.

See copilot/agents/system_health.py for the reference implementation.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from ..llm.fallback_client import LLMClient
from ..models import AgentRun
from ..repositories import AgentRunRepository
from ..tools.base import PlannedStep, ToolResult
from ..tools.registry import ToolRegistry
from ..tools.registry import tool_registry as default_tool_registry

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    name: str = ""
    description: str = ""

    def __init__(
        self,
        *,
        tools: ToolRegistry | None = None,
        llm: LLMClient | None = None,
        run_repository: AgentRunRepository | None = None,
    ):
        self.tools = tools or default_tool_registry
        # Tries Groq first, then falls back to Google's Gemini, then
        # OpenRouter, if the earlier providers are exhausted or
        # unconfigured -- see llm/fallback_client.py.
        self.llm = llm or LLMClient()
        self.runs = run_repository or AgentRunRepository()

    # --- Subclasses implement these ------------------------------------

    @abstractmethod
    def observe(self) -> dict:
        """Gather whatever raw context this agent needs before deciding
        what to do. Must have no side effects -- for agents whose real
        "observation" is itself a set of read-only tool calls (e.g.
        SystemHealthAgent pinging services), it's fine for this to return
        {} and let plan()/execute() do the actual gathering; the tool
        calls still get logged either way."""

    @abstractmethod
    def reason(self, observation: dict) -> str:
        """A human-readable explanation of what the observation means.
        May call self.llm if self.llm.is_configured, but must have a
        working deterministic fallback when it isn't -- this app must
        never hard-fail just because no LLM key is set."""

    @abstractmethod
    def plan(self, observation: dict, reasoning: str) -> list[PlannedStep]:
        """Decide what to do next, as an ordered list of tool calls."""

    @abstractmethod
    def verify(self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]]) -> bool:
        """Did executing the plan actually achieve what it set out to?"""

    # --- Shared orchestration -------------------------------------------

    def execute(self, plan: list[PlannedStep], run: AgentRun) -> list[tuple[PlannedStep, ToolResult]]:
        results = []
        for step in plan:
            # An unknown tool name is a genuine planning bug -- looked up
            # outside the try below so it still aborts the whole run (see
            # test_agent_run_marked_failed_when_plan_references_unknown_tool).
            tool = self.tools.get(step.tool_name)
            started = time.monotonic()
            try:
                result = tool.run(**step.tool_input)
            except Exception as exc:
                # BaseTool promises never to raise, but one tool breaking
                # that promise (e.g. a DB outage mid-query) shouldn't abort
                # the rest of the plan -- record it as a failed step and
                # keep going, same principle as chat's _run_tool guard.
                logger.exception("Tool %r raised during %s's plan instead of returning a failed ToolResult", step.tool_name, self.name)
                result = ToolResult(success=False, error=f"{step.tool_name} failed unexpectedly: {exc}")
            duration_ms = int((time.monotonic() - started) * 1000)

            log = self.runs.log_tool_call(run, tool_name=step.tool_name, tool_input=step.tool_input, result=result)
            log.duration_ms = duration_ms
            log.save(update_fields=["duration_ms"])

            results.append((step, result))
        return results

    def report(
        self,
        *,
        agent_run: AgentRun,
        observation: dict,
        reasoning: str,
        plan: list[PlannedStep],
        tool_results: list[tuple[PlannedStep, ToolResult]],
        verified: bool,
    ) -> str:
        """Default report is a simple templated summary; override for
        something richer (e.g. an LLM-written paragraph)."""
        step_lines = [
            f"- {step.tool_name}: {'ok' if result.success else 'FAILED: ' + result.error}"
            for step, result in tool_results
        ]
        status = "Verified" if verified else "Completed with unverified results"
        return f"{status}. {reasoning}\n" + "\n".join(step_lines)

    def confidence(
        self, observation: dict, tool_results: list[tuple[PlannedStep, ToolResult]], verified: bool
    ) -> float:
        """Default heuristic: the fraction of tool calls that succeeded,
        discounted if verify() didn't pass. Override for something
        smarter (e.g. based on how much underlying data was available)."""
        if not tool_results:
            return 1.0 if verified else 0.5
        success_rate = sum(1 for _, result in tool_results if result.success) / len(tool_results)
        return round(success_rate if verified else success_rate * 0.6, 2)

    def run(self, *, trigger: str = "manual", requested_by=None) -> AgentRun:
        agent_run = self.runs.start(agent_name=self.name, trigger=trigger, requested_by=requested_by)
        try:
            observation = self.observe()
            reasoning = self.reason(observation)
            plan = self.plan(observation, reasoning)
            tool_results = self.execute(plan, agent_run)
            verified = self.verify(observation, tool_results)
            result_summary = self.report(
                agent_run=agent_run,
                observation=observation,
                reasoning=reasoning,
                plan=plan,
                tool_results=tool_results,
                verified=verified,
            )

            self.runs.complete(
                agent_run,
                observation_summary=self._summarize_observation(observation),
                reasoning_summary=reasoning,
                plan=[{"tool_name": s.tool_name, "tool_input": s.tool_input, "reason": s.reason} for s in plan],
                result_summary=result_summary,
                confidence=self.confidence(observation, tool_results, verified),
            )
        except Exception as exc:
            logger.exception("Agent %s run %s failed", self.name, agent_run.id)
            self.runs.fail(agent_run, error=str(exc))
        return agent_run

    def _summarize_observation(self, observation: dict) -> str:
        if not observation:
            return ""
        return ", ".join(f"{k}={v}" for k, v in observation.items())[:2000]
