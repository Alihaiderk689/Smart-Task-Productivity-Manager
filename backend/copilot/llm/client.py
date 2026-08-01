"""Thin wrapper around the Groq chat-completions API (OpenAI-compatible),
used for the Admin Copilot's LLM-backed reasoning and chat. Every agent
that wants LLM reasoning checks `client.is_configured` first and falls back
to a deterministic summary when it's False -- see agents/system_health.py
for the reference pattern. Nothing in this app should hard-crash just
because GROQ_API_KEY hasn't been set yet.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama-3.3-70b-versatile"


class LLMNotConfiguredError(RuntimeError):
    """Raised only if calling code skips the `is_configured` check --
    that check exists specifically so callers can fall back gracefully
    instead of needing to handle this exception routinely."""


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = ""

    @property
    def wants_tool_call(self) -> bool:
        return bool(self.tool_calls)


class GroqClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL or DEFAULT_MODEL
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
        return self._client

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        if not self.is_configured:
            raise LLMNotConfiguredError(
                "GROQ_API_KEY is not set -- check `client.is_configured` before calling chat()."
            )

        client = self._get_client()
        kwargs = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if max_tokens:
            kwargs["max_completion_tokens"] = max_tokens

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments)
                if not isinstance(arguments, dict):
                    # Valid JSON but not an object -- e.g. the model emits the bare
                    # string "null" for a tool with no required arguments. Still
                    # has to become {} so callers can always safely **-unpack it.
                    raise TypeError
            except (json.JSONDecodeError, TypeError):
                logger.warning("Groq returned non-object tool arguments for %s: %r", call.function.name, call.function.arguments)
                arguments = {}
            tool_calls.append(ToolCallRequest(id=call.id, name=call.function.name, arguments=arguments))

        return ChatResult(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "",
        )

    def summarize(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        """Plain text-in, text-out convenience wrapper for the common
        "explain this data in plain English" case -- no tool-calling."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        result = self.chat(messages, temperature=temperature)
        return result.content
