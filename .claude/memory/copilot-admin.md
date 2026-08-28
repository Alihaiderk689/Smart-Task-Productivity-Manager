---
name: copilot-admin
description: Agentic AI Admin Copilot — 8 autonomous agents + live chat, Groq→Gemini→OpenRouter fallback LLM chain, tool registry with sensitive/safe permission split, approval-gated mutations.
app: copilot
updated: 2026-08-28
---

## What it does

Staff-only (`IsAdminUser` throughout) LLM-driven admin assistant: 8
autonomous agents that run on a schedule and raise findings/
recommendations, plus a live chat at `/admin/copilot`. Built
"foundation first" — see [ARCHITECTURE.md](../../ARCHITECTURE.md)'s "Why
a services/tools layer" section for why this app doesn't just call the
ORM directly.

## Key files

- `tools/base.py` — `BaseTool` (name, description, JSON-schema
  `input_schema`, `permission`: `None`=safe or `"sensitive"`=mutates and
  can only run via an approved `Recommendation`). **Contract: `run()`
  must never raise** — callers defensively catch anyway, but a new tool
  should still return `ToolResult(success=False, ...)` on its own errors.
- `tools/registry.py` — the one process-wide `tool_registry`, populated in
  `apps.py::ready()`.
- `tools/{action,analytics,database,reminder,system,task,user}_tools.py`
  — the actual tool implementations, one file per domain.
- `agents/base.py` — `BaseAgent`: every agent implements Observe → Reason
  → Plan → Execute → Verify → Report. `execute()` isolates a per-tool
  exception into a failed `ToolResult` instead of aborting the whole plan.
- `agents/{system_health,analytics,user_monitoring,task_intelligence,
  reminder,database_intelligence,recommendation,action}.py` — the 8
  agents. `recommendation.py` is the meta/digest agent; `action.py`
  executes approved recommendations and **never decides anything on its
  own**, just replays `action_payload`.
- `llm/client.py` (`GroqClient`), `llm/gemini_client.py`
  (`GeminiClient`), `llm/openrouter_client.py` (`OpenRouterClient`) — same
  shape, both Gemini/OpenRouter reuse the `openai` package pointed at a
  different `base_url` since both providers expose OpenAI-compatible
  endpoints. `llm/fallback_client.py` (`LLMClient`) is the single entry
  point every agent and chat service actually uses: Groq first (own
  per-minute retry/backoff) → Gemini → OpenRouter, each only consulted if
  configured and only after the previous one's retries are exhausted.
  **Every LLM call must check `is_configured` first and have a
  deterministic fallback** — nothing in this app may hard-crash for lack
  of a key.
- `services/chat_service.py` — the live-chat service (admin tier; compare
  [usercopilot.md](usercopilot.md)'s `UserChatService`).
- `models.py` — `AgentRun`, `ToolCallLog` (durable record of every tool
  call any agent or chat has ever made — what makes
  [evaluation.md](evaluation.md)'s metrics computable after the fact),
  `ConversationMessage`, `Recommendation`.
- `tasks.py` — the per-agent entry points called by
  [core-infra.md](core-infra.md)'s `run_scheduled_tasks` job groups.

## Chat: why it has no path to a destructive action

Real Groq function-calling, but **sensitive tools are excluded from its
tool schema entirely** — not just prompted against. The only way chat can
cause a mutation is calling `propose_action`
(`tools/action_tools.py`), which creates a `pending` `Recommendation` for
a human to separately approve. The system prompt lists sensitive tool
names/schemas explicitly so the model doesn't have to guess what exists.

## Approval workflow

`POST /api/copilot/recommendations/<id>/approve|reject/`. Approving
executes **immediately** via `ActionAgent` scoped to just that one
recommendation; the `action_agent_sweep` Celery Beat / scheduled-tasks job
catches anything approved but not yet executed (e.g. the approve request
died before triggering execution).

## Sensitive (approval-gated) tools

`deactivate_user`, `send_reminder`, `delete_completed_tasks`. If you add a
new tool that mutates data, default to `permission="sensitive"` unless
you have a specific reason an LLM should be able to trigger it
unsupervised.

## Gotchas

- **`Recommendation.action_payload` is a plain JSON blob**, no FK/cascade
  to the user/task it references. Deleting the referenced object leaves
  an orphaned recommendation behind unless something explicitly cleans it
  up. Never approve/execute one without confirming what it actually
  points at.
- **Groq free tier has a *daily* token quota**, not just per-minute —
  heavy session-long testing can exhaust it (`429 ... TPD`). The system
  degrades gracefully (falls through to Gemini/OpenRouter if configured,
  or fails the individual call), but don't mistake quota exhaustion for a
  code bug.
- Backend venv is **3.9** — `str | None` needs
  `from __future__ import annotations`; `list[str]`/`dict[str,int]`
  generics work natively (PEP 585).

## Touches / related

[usercopilot.md](usercopilot.md) (same LLM chain, user-tier tool
surface), [evaluation.md](evaluation.md) (grades this app's real
behavior), [core-infra.md](core-infra.md) (schedules every agent's sweep),
[adminpanel.md](adminpanel.md) (parallel direct-action path to some of
the same effects).
