"""Thin wrapper around OpenRouter -- a third fallback provider, tried after
both Groq and Gemini are exhausted/unconfigured (see
fallback_client.py::LLMClient). Deliberately shaped as a drop-in peer to
GroqClient/GeminiClient: same ChatResult/ToolCallRequest return types, same
chat() signature -- so LLMClient can treat all three interchangeably
without any chat_service needing to know which one actually served a given
request.

OpenRouter's chat completions endpoint is itself OpenAI-compatible (it
proxies to whichever underlying model you pick), so this reuses the
`openai` package pointed at OpenRouter's base_url, same trick as the Gemini
client.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

from .client import ChatResult, ToolCallRequest

logger = logging.getLogger(__name__)

# Override via OPENROUTER_MODEL in .env for a different underlying model --
# see https://openrouter.ai/models for the full catalog.
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterNotConfiguredError(RuntimeError):
    """Raised only if calling code skips the `is_configured` check --
    mirrors client.py's LLMNotConfiguredError."""


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.model = model or settings.OPENROUTER_MODEL or DEFAULT_OPENROUTER_MODEL
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=OPENROUTER_BASE_URL)
        return self._client

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        if not self.is_configured:
            raise OpenRouterNotConfiguredError(
                "OPENROUTER_API_KEY is not set -- check `client.is_configured` before calling chat()."
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
                logger.warning("OpenRouter returned non-object tool arguments for %s: %r", call.function.name, call.function.arguments)
                arguments = {}
            tool_calls.append(ToolCallRequest(id=call.id, name=call.function.name, arguments=arguments))

        return ChatResult(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "",
        )
