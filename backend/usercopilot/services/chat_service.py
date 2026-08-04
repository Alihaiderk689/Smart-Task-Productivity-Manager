"""Chat orchestrator for the User Copilot -- turns a free-form message from
the CURRENTLY AUTHENTICATED user into an LLM response, calling that one
user's own tools along the way (see tools/registry.py::for_user). Fully
stateless: no ConversationMessage-equivalent model, no DB persistence of
any kind -- the caller (the chat endpoint) resends the conversation's
recent history with every request, the same way OpenAI/Anthropic-style
chat APIs work. This is deliberate, per the "do NOT permanently save chat
history" requirement -- session-only memory, entirely client-held.
"""

from __future__ import annotations

import json
import logging

from copilot.llm.fallback_client import LLMClient

from ..services.category_resolver import list_category_names
from ..services.date_resolver import current_context_line
from ..tools.registry import tool_registry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
MAX_HISTORY_MESSAGES = 20
FALLBACK_REPLY = "I gathered some information but couldn't finish reasoning about it -- try rephrasing your question."
LLM_OUTAGE_REPLY = "I'm having trouble reaching the AI service right now -- please try again in a moment."

BASE_SYSTEM_PROMPT = (
    "You are TaskFlow Copilot, a personal task assistant for the CURRENTLY LOGGED-IN user only. "
    "You can only see and act on this one user's own tasks and categories -- you have no access "
    "to any other user's data, and no admin capabilities of any kind. Be concise, friendly, and "
    "conversational.\n\n"
    "Only call a tool once you actually have everything it needs. If the user hasn't given you a "
    "required piece of information yet (e.g. a task's title, category, start time, or end time "
    "for create_task), ask them for it in plain text instead of guessing or calling the tool "
    "anyway -- keep asking, one question at a time, until you have everything, then call the "
    "tool. Remember what's already been given earlier in this same conversation; don't re-ask "
    "for something the user already told you.\n\n"
    "NEVER call delete_task with confirmed=true in the same turn the user first asks to delete "
    "something -- always ask them to confirm in plain text first, and only pass confirmed=true "
    "once they've explicitly said yes/confirm in a later message.\n\n"
    "If a tool result's data has status 'needs_category_confirmation' or 'needs_confirmation', "
    "relay its message to the user as a question and stop -- wait for their answer before doing "
    "anything else.\n\n"
    "Never claim to have done something you didn't actually do -- only describe what a tool "
    "result actually says happened. If a tool call fails, say so plainly rather than making up "
    "an answer. You may use light Markdown (lists, **bold**) in your replies."
)


class ChatNotConfiguredError(RuntimeError):
    """Raised only if calling code skips the `is_configured` check --
    mirrors copilot.services.chat_service's identical guard."""


class UserChatService:
    def __init__(self, *, llm: LLMClient | None = None):
        # LLMClient tries Groq first (retrying through its own per-minute
        # rate limit), then falls back to Google's Gemini, then OpenRouter,
        # if the earlier providers are exhausted or unconfigured -- see
        # copilot/llm/fallback_client.py.
        self.llm = llm or LLMClient()

    @property
    def is_configured(self) -> bool:
        return self.llm.is_configured

    def _system_prompt(self, user) -> str:
        categories = list_category_names(user)
        cat_line = (
            f"This user's existing categories: {', '.join(categories)}."
            if categories
            else "This user has no categories yet -- any category they mention will need to be created (ask first)."
        )
        return f"{BASE_SYSTEM_PROMPT}\n\n{current_context_line()}\n{cat_line}"

    def _run_tool(self, tools: dict, name: str, arguments: dict) -> dict:
        tool = tools.get(name)
        if tool is None:
            return {"success": False, "error": f"Tool {name!r} is not available.", "data": None}
        try:
            return tool.run(**arguments).to_dict()
        except Exception:
            # BaseTool promises never to raise, but the chat loop must stay
            # up even if a tool breaks that promise -- never leak the real
            # exception text back to the model/user.
            logger.exception("User copilot tool %r raised instead of returning a failed ToolResult", name)
            return {"success": False, "error": f"{name} failed unexpectedly.", "data": None}

    def send(self, *, user, message: str, history: list[dict] | None = None) -> dict:
        if not self.is_configured:
            raise ChatNotConfiguredError("Neither GROQ_API_KEY nor GEMINI_API_KEY is configured.")

        # Fresh, user-bound tool instances for this request only -- never
        # cached or shared across requests/users (see registry.for_user).
        tools = tool_registry.for_user(user)
        tools_schema = tool_registry.schemas()

        trimmed_history = (history or [])[-MAX_HISTORY_MESSAGES:]
        messages = [{"role": "system", "content": self._system_prompt(user)}]
        messages += [{"role": h["role"], "content": h["content"]} for h in trimmed_history]
        messages.append({"role": "user", "content": message})

        tool_trace: list[dict] = []
        reply = FALLBACK_REPLY
        # Scoped to this one send() call only -- if the model calls the
        # exact same tool with the exact same arguments more than once in
        # one turn (seen in practice after a rate-limited retry: the model
        # re-sees its own successful tool result and, instead of just
        # confirming, calls it again -- e.g. create_task firing twice for
        # one request), reuse the first result instead of repeating a
        # mutation. Harmless no-op for read-only tools called twice.
        seen_calls: dict[str, dict] = {}

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                result = self.llm.chat(messages, tools=tools_schema)
            except Exception:
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
                cache_key = f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"
                if cache_key in seen_calls:
                    tool_result = seen_calls[cache_key]
                    logger.info("Skipped re-running duplicate tool call %r in the same turn", call.name)
                else:
                    tool_result = self._run_tool(tools, call.name, call.arguments)
                    seen_calls[cache_key] = tool_result
                tool_trace.append({"tool": call.name, "input": call.arguments, "output": tool_result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(tool_result)})
        else:
            reply = FALLBACK_REPLY

        return {"reply": reply, "tool_calls": tool_trace}
