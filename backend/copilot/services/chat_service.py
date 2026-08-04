"""Chat orchestrator -- turns a free-form admin message into an LLM
response, optionally calling read-only tools along the way. The LLM's only
means of causing a mutation is calling propose_action (see
tools/action_tools.py), which creates a pending Recommendation for a human
to separately approve; every genuinely sensitive tool is deliberately left
out of the schema handed to the model here, so there is no path from chat
straight to a data-changing tool call, even a hallucinated one.
"""

from __future__ import annotations

import json
import logging

from ..llm.fallback_client import LLMClient
from ..memory.service import MemoryService
from ..tools.registry import ToolRegistry
from ..tools.registry import tool_registry as default_tool_registry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the Admin Copilot for a task-management app called TaskFlow. You help the admin "
    "understand the state of the system by calling the read-only tools available to you. "
    "You must NEVER claim to have performed an action yourself. If the admin asks you to do "
    "something that changes data (deactivate a user, send a reminder, etc.), call the "
    "propose_action tool instead of doing it yourself -- this creates a pending recommendation "
    "that a human admin must separately review and approve. Be concise and factual; base answers "
    "only on tool results, not guesses. If a tool call fails, say so plainly rather than making "
    "up an answer.\n\n"
    "propose_action's 'tool' argument must be the EXACT name of one of the actions listed below "
    "-- never invent a plausible-sounding tool name, and never substitute a different action "
    "just because nothing listed matches. If the admin asks for something none of these actions "
    "can do (e.g. renaming a user, editing a task's title), say plainly that this isn't something "
    "you're able to do yet -- do not propose a different, unrelated action instead, even a "
    "seemingly related or lower-risk one."
)

MAX_TOOL_ROUNDS = 4
FALLBACK_REPLY = "I gathered some information but couldn't finish reasoning about it -- try rephrasing your question."
LLM_OUTAGE_REPLY = "I'm having trouble reaching the AI service right now -- please try again in a moment."


class ChatNotConfiguredError(RuntimeError):
    """Raised only if calling code skips the `is_configured` check on the
    underlying LLMClient -- mirrors llm.client.LLMNotConfiguredError."""


class ChatService:
    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        memory: MemoryService | None = None,
        tools: ToolRegistry | None = None,
    ):
        # LLMClient tries Groq first, retrying through its own per-minute
        # rate limit, then falls back to Google's Gemini, then OpenRouter,
        # if the earlier providers are exhausted or unconfigured -- see
        # llm/fallback_client.py. Retry/backoff no longer lives here; this
        # just calls .chat() and reacts to whether it succeeded.
        self.llm = llm or LLMClient()
        self.memory = memory or MemoryService()
        self.tools = tools or default_tool_registry

    @property
    def is_configured(self) -> bool:
        return self.llm.is_configured

    def _chat_tools_schema(self) -> list[dict]:
        # Only non-sensitive tools ever get handed to the model -- a
        # sensitive tool can only run via an admin-approved Recommendation.
        return [t.to_llm_schema() for t in self.tools.all() if not t.is_sensitive]

    def _system_prompt(self) -> str:
        # Sensitive tools are deliberately excluded from the schema above,
        # but propose_action still needs their exact name to reference --
        # without this, the model has to guess a plausible snake_case name
        # (it sometimes guesses right, e.g. "deactivate_user", but that's
        # luck, not a contract). Listing them here makes tool selection for
        # propose_action deterministic instead of a naming-convention bet.
        sensitive_tools = [t for t in self.tools.all() if t.is_sensitive]
        if not sensitive_tools:
            return SYSTEM_PROMPT
        lines = [
            f"- {t.name}: {t.description} Arguments: {json.dumps(t.input_schema.get('properties', {}))}"
            for t in sensitive_tools
        ]
        return SYSTEM_PROMPT + "\n\nActions available via propose_action (use the exact tool name):\n" + "\n".join(lines)

    def _run_tool(self, name: str, arguments: dict) -> dict:
        if name not in self.tools:
            return {"success": False, "error": f"Tool {name!r} is not available."}
        tool = self.tools.get(name)
        if tool.is_sensitive:
            return {"success": False, "error": f"Tool {name!r} is not available for direct chat use -- use propose_action instead."}
        try:
            return tool.run(**arguments).to_dict()
        except Exception as exc:
            # BaseTool promises never to raise, but chat must stay up even
            # if a tool breaks that promise (e.g. a DB outage mid-query).
            logger.exception("Tool %r raised during chat instead of returning a failed ToolResult", name)
            return {"success": False, "error": f"{name} failed unexpectedly: {exc}"}

    def send(self, *, user, message: str, session_id: str = "default") -> dict:
        if not self.is_configured:
            raise ChatNotConfiguredError("Neither GROQ_API_KEY nor GEMINI_API_KEY is configured.")

        self.memory.add_message(user=user, content=message, role="admin", session_id=session_id)

        history = self.memory.to_llm_messages(user=user, session_id=session_id, limit=20)
        messages = [{"role": "system", "content": self._system_prompt()}] + history
        tools_schema = self._chat_tools_schema()

        tool_trace = []
        proposed_recommendation = None
        proposed_recommendations = []
        reply = FALLBACK_REPLY

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                result = self.llm.chat(messages, tools=tools_schema)
            except Exception:
                # No provider in the chain could serve this (Groq
                # exhausted/down, and Gemini/OpenRouter either also failed
                # or aren't configured) -- fail the turn gracefully rather
                # than a 500, same principle as every agent's LLM fallback
                # (see agents/system_health.py).
                reply = LLM_OUTAGE_REPLY
                break

            if not result.wants_tool_call:
                reply = result.content or "I don't have anything more to add."
                break

            messages.append({
                "role": "assistant",
                "content": result.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in result.tool_calls
                ],
            })

            for call in result.tool_calls:
                tool_result = self._run_tool(call.name, call.arguments)
                if call.name == "propose_action" and tool_result.get("success"):
                    # A single exchange can call propose_action more than
                    # once (e.g. proposing several users in one turn) --
                    # keep every one of them, not just whichever happened
                    # last, so a caller cleaning up after itself (see
                    # evaluation/fixtures.py) can actually find them all.
                    proposed_recommendation = tool_result.get("data")
                    proposed_recommendations.append(tool_result.get("data"))

                tool_trace.append({"tool": call.name, "input": call.arguments, "output": tool_result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(tool_result)})
        else:
            reply = FALLBACK_REPLY

        self.memory.add_message(user=user, content=reply, role="agent", session_id=session_id)
        return {
            "reply": reply,
            "tool_calls": tool_trace,
            "proposed_recommendation": proposed_recommendation,
            "proposed_recommendations": proposed_recommendations,
        }
