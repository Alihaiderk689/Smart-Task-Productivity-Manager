---
name: usercopilot
description: The admin copilot duplicated at the regular-user trust tier — its own tool set scoped to the calling user's own tasks/categories, no path to any admin-only action.
app: usercopilot
updated: 2026-08-28
---

## What it does

Same idea as [copilot-admin.md](copilot-admin.md) (LLM chat via the same
`LLMClient` fallback chain) but for **any authenticated user**, not just
staff — `IsAuthenticated`, not `IsAdminUser`. Lives at `chat_send` /
`status_view` in `backend/usercopilot/views.py`.

## Why it's a separate app, not a permission check bolted onto `copilot`

Deliberate duplication (see [ARCHITECTURE.md](../../ARCHITECTURE.md)'s
Authorization section): this app's tool surface only ever touches the
*calling* user's own tasks/categories — no tool shaped like
`deactivate_user` should ever exist at this trust tier, approved or not.
Keeping it a fully separate app/tool-set makes that guarantee structural
rather than something a permission check could get wrong.

## Key files

- `backend/usercopilot/views.py` — `chat_send`, `status_view`.
- `backend/usercopilot/models.py`, `serializers.py` — its own
  conversation/message models, parallel to `copilot`'s but not shared.
- Tools/services live under `copilot`'s package structure conceptually
  (same `LLMClient`) but bound to `request.user` per the chat handler —
  see `tools/registry.py` in the `copilot` app for how tools get scoped
  to a specific user at call time.

## Endpoints

`POST /api/usercopilot/chat/` (`chat_send`) — validates via
`ChatRequestSerializer`, delegates to `UserChatService().send(user=...,
message=..., history=...)`. Returns `503` with a fixed "ask an admin to
set GROQ_API_KEY" detail message if unconfigured, `500` with a generic
message on any unexpected exception (**never leaks the raw exception/
stack trace to the client** — logs it server-side instead).
`GET /api/usercopilot/status/` — `{"llm_configured": bool}`.

## Touches / related

[copilot-admin.md](copilot-admin.md) (shares the LLM fallback chain and
the general chat architecture — read that file first for the deeper
mechanics), [tasks.md](tasks.md) / [categories.md](categories.md) (the
only two domains its tools can touch).
