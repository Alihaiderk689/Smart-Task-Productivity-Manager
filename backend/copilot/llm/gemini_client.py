"""Thin wrapper around Google's Gemini API -- used as the fallback provider
when Groq's calls are exhausted (see fallback_client.py::LLMClient).
Deliberately shaped as a drop-in peer to GroqClient: same ChatResult/
ToolCallRequest return types, same chat() signature -- so LLMClient can
treat the two interchangeably without either chat_service needing to know
which one actually served a given request.

Gemini exposes an OpenAI-compatible chat completions endpoint, so this
reuses the `openai` package pointed at Google's base_url instead of needing
a bespoke SDK -- Google's own documented recommended integration approach.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

from .client import ChatResult, ToolCallRequest

logger = logging.getLogger(__name__)

# "gemini-flash-latest" is Google's maintained alias for its current
# recommended flash model rather than a pinned version -- avoids hardcoding
# a specific model that Google can later retire for new accounts (as
# happened with "gemini-2.5-flash", the previous default here). Override
# via GEMINI_MODEL in .env for a pinned version instead.
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiNotConfiguredError(RuntimeError):
    """Raised only if calling code skips the `is_configured` check --
    mirrors client.py's LLMNotConfiguredError."""


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL or DEFAULT_GEMINI_MODEL
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=GEMINI_BASE_URL)
        return self._client

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        if not self.is_configured:
            raise GeminiNotConfiguredError(
                "GEMINI_API_KEY is not set -- check `client.is_configured` before calling chat()."
            )

        client = self._get_client()
        kwargs = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments)
                if not isinstance(arguments, dict):
                    raise TypeError
            except (json.JSONDecodeError, TypeError):
                logger.warning("Gemini returned non-object tool arguments for %s: %r", call.function.name, call.function.arguments)
                arguments = {}
            tool_calls.append(ToolCallRequest(id=call.id, name=call.function.name, arguments=arguments))

        return ChatResult(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "",
        )
