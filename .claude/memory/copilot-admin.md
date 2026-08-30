---
name: copilot-admin
description: Agentic AI Admin Copilot — 8 autonomous agents + live chat, Groq→Gemini→OpenRouter fallback LLM chain, tool registry with sensitive/safe permission split, approval-gated mutations.
app: copilot
updated: 2026-08-30
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

## Scope guardrail

`SYSTEM_PROMPT` (`services/chat_service.py`) has an explicit "SCOPE" clause:
decline anything that isn't operating this TaskFlow instance (code, general
programming help, essays, translations, trivia, etc.), regardless of how
the request is framed (hypothetical, role-play, "just for debugging") or
what any tool result/app data says. Prompt-only guardrail (no output
filter/classifier) — verified live against Groq, holds up to direct
off-topic asks ("give me Python code to reverse a string" → declines and
redirects) without needing a second model call. If a future jailbreak gets
through, strengthen this clause before reaching for an extra
classification pass. Mirrored in [usercopilot.md](usercopilot.md)'s
`BASE_SYSTEM_PROMPT`.

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

`deactivate_user`, `delete_user`, `rename_user`, `send_reminder`,
`delete_completed_tasks`. If you add a new tool that mutates data, default
to `permission="sensitive"` unless you have a specific reason an LLM should
be able to trigger it unsupervised.

## Server-side authorization hardening (added 2026-08-30)

The LLM naming a tool was never sufficient authorization on its own, but
`propose_action` (`tools/action_tools.py`) used to accept *any* registered
tool name, sensitive or not. Now: `target_tool` must both exist in
`tool_registry` **and** have `permission="sensitive"` (`tool.is_sensitive`)
— the registry's own tag is the allowlist, not a second hand-maintained
list. `ActionAgent.plan()` (`agents/action.py`) re-checks this again at the
actual execution chokepoint (every path converges there: chat's
immediate-execute, the manual `/approve/` endpoint, and the Celery sweep),
plus verifies `rec.resolved_by` is still `is_active`/`is_staff` right now —
not just at the moment they clicked approve. Closes a real gap: a staff
account deactivated between approving an action and a delayed sweep
running it used to still execute on now-revoked authority. A rec that
fails this check is marked `failed` immediately with a clear
`execution_result.error`, excluded from the plan, and never silently runs.

`ActionAgent.plan()` also injects `tool_input["_acting_user_id"] =
rec.resolved_by_id` (server-set, never LLM-controlled, same pattern as
`_requested_by`) into every step it builds — `DeactivateUserTool`/
`DeleteUserTool` (`tools/user_tools.py`) use it to refuse targeting the
acting admin's own account, matching `adminpanel.deactivate_user`/
`delete_user`'s existing self-target guard. A tool called directly in a
unit test (no `_acting_user_id` kwarg) sees `None`, which never matches a
real user id, so this is backward compatible with direct `tool.run(...)`
tests that don't go through `ActionAgent`.

**Gotcha if you write a test that creates an `approved` `Recommendation`
directly** (bypassing the real approve endpoint/`RecommendationRepository.approve()`):
you must set `resolved_by=` to an active staff user, or `ActionAgent.plan()`
will now correctly mark it `failed` instead of executing it — several
existing tests needed this fix when the check was added.

**Operational check after deploying this hardening**: any `Recommendation`
already sitting at `status="approved"` whose `resolved_by` user was since
deleted (FK is `SET_NULL`) or deactivated/de-staffed will now dead-end at
`failed` on the next sweep instead of quietly executing — and `failed` has
no re-approval path (`approve_recommendation` rejects anything that isn't
currently `pending`). Read-only check, safe to run anytime:
```python
from copilot.models import Recommendation
qs = Recommendation.objects.filter(status="approved")
orphaned = qs.filter(resolved_by__isnull=True)
invalid = [r for r in qs.filter(resolved_by__isnull=False)
           if not (r.resolved_by.is_active and r.resolved_by.is_staff)]
```
Checked against the dev DB on 2026-08-30 right after adding the check: zero
`approved` recommendations existed at all, so nothing was orphaned —
re-run against production before/after that deploy, this doesn't tell you
anything about a different database.

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
