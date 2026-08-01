"""Conversation memory -- persisted in Postgres (ConversationMessage), not
in-process, so it survives across requests/sessions/restarts as required.
No chat agent exists yet to populate this (that's a follow-up piece), but
the model + service are built now since the memory layer is foundational
and other agents' `run()` calls don't depend on chat existing first."""

from __future__ import annotations

from ..models import ConversationMessage

# Groq/OpenAI-style role names differ from ours -- ours describe *who*
# ("admin" vs "agent"); theirs describe the chat-API's notion of turn owner.
_ROLE_TO_LLM = {"admin": "user", "agent": "assistant"}


class MemoryService:
    def add_message(
        self, *, user, content: str, role: str, session_id: str = "default", related_agent_run=None
    ) -> ConversationMessage:
        return ConversationMessage.objects.create(
            user=user,
            content=content,
            role=role,
            session_id=session_id,
            related_agent_run=related_agent_run,
        )

    def recent_history(self, *, user, session_id: str = "default", limit: int = 20) -> list[ConversationMessage]:
        newest_first = ConversationMessage.objects.filter(user=user, session_id=session_id).order_by("-created_at")[:limit]
        return list(reversed(newest_first))

    def to_llm_messages(self, *, user, session_id: str = "default", limit: int = 20) -> list[dict]:
        """Conversation history in the {"role", "content"} shape Groq's
        chat API expects, oldest first."""
        return [
            {"role": _ROLE_TO_LLM.get(m.role, m.role), "content": m.content}
            for m in self.recent_history(user=user, session_id=session_id, limit=limit)
        ]
