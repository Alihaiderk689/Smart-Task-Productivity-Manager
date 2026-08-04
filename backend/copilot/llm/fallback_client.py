"""Single entry point every chat service in this app (admin copilot and
user copilot both) should use instead of instantiating GroqClient
directly -- tries Groq first (with its own per-minute-rate-limit
backoff/retry), then falls back to Google's Gemini (gemini_client.py), then
to OpenRouter (openrouter_client.py) if the earlier providers are exhausted
or unconfigured. This is now the one place retry-and-fallback policy
lives, instead of being duplicated per chat service.

Same public shape as GroqClient (`is_configured`, `chat(...)`) so it's a
drop-in replacement wherever `self.llm = llm or GroqClient()` used to be.
"""

from __future__ import annotations

import logging
import time

from .client import ChatResult, GroqClient, LLMNotConfiguredError
from .gemini_client import GeminiClient
from .openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
# Only applied between attempts on a 429 (rate limit) -- see the identical
# rationale previously duplicated in each chat_service.py, now centralized
# here. Non-rate-limit failures still fail fast, no artificial delay.
RATE_LIMIT_BACKOFF_SECONDS = [2, 6]


def _is_rate_limited(exc: Exception) -> bool:
    # Duck-typed on purpose: groq.RateLimitError and openai.RateLimitError
    # (used by both the Gemini and OpenRouter clients) all set
    # `.status_code = 429` on their shared APIStatusError base -- checking
    # the attribute instead of importing every provider's exception class
    # keeps this file from needing to know which SDK actually raised it.
    return getattr(exc, "status_code", None) == 429


class LLMClient:
    def __init__(
        self,
        *,
        groq: GroqClient | None = None,
        gemini: GeminiClient | None = None,
        openrouter: OpenRouterClient | None = None,
    ):
        # Tried in this order: Groq -> Gemini -> OpenRouter. Each is only
        # ever consulted if it's configured, so leaving any of them unset
        # in .env just shortens the chain -- with none configured, chat()
        # raises LLMNotConfiguredError.
        self.groq = groq or GroqClient()
        self.gemini = gemini or GeminiClient()
        self.openrouter = openrouter or OpenRouterClient()

    @property
    def _providers_in_order(self):
        return [self.groq, self.gemini, self.openrouter]

    @property
    def is_configured(self) -> bool:
        return any(p.is_configured for p in self._providers_in_order)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        configured = [p for p in self._providers_in_order if p.is_configured]
        if not configured:
            raise LLMNotConfiguredError(
                "None of GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY is configured."
            )

        for i, provider in enumerate(configured):
            is_last = i == len(configured) - 1
            try:
                return self._chat_with_backoff(provider, messages, tools, temperature, max_tokens)
            except Exception as exc:
                if is_last:
                    # No provider left to try -- let the original exception
                    # from whichever one just failed propagate, same as a
                    # single-provider setup always has.
                    raise
                next_provider = type(configured[i + 1]).__name__
                logger.warning("%s unavailable after retries, falling back to %s: %s", type(provider).__name__, next_provider, exc)

    def summarize(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        """Plain text-in, text-out convenience wrapper (mirrors GroqClient's)
        -- goes through the same Groq -> Gemini -> OpenRouter chat() above,
        so callers (every agent's report()) get the fallback for free."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        result = self.chat(messages, temperature=temperature)
        return result.content

    def _chat_with_backoff(self, client, messages, tools, temperature, max_tokens) -> ChatResult:
        provider = type(client).__name__
        last_error: Exception | None = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                return client.chat(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)
            except Exception as exc:
                last_error = exc
                if _is_rate_limited(exc):
                    logger.warning("%s rate-limited (attempt %s/%s): %s", provider, attempt, RETRY_ATTEMPTS, exc)
                    if attempt < RETRY_ATTEMPTS:
                        backoff = RATE_LIMIT_BACKOFF_SECONDS[min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)]
                        time.sleep(backoff)
                    continue
                logger.warning("%s chat call failed (attempt %s/%s): %s", provider, attempt, RETRY_ATTEMPTS, exc)
        raise last_error
