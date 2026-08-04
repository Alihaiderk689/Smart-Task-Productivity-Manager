# CLAUDE.md

Project-specific notes for Claude Code. User-facing feature docs live in
[README.md](README.md) (core task manager) and [backend/README_AUTH.md](backend/README_AUTH.md)
(auth endpoints) — this file is oriented toward working in the codebase:
architecture, conventions, dev-environment quirks, and gotchas discovered
while building it out.

## What this is

A full-stack task manager (Django REST Framework + React/Vite) that has
grown well past "task CRUD": JWT + Google OAuth auth with OTP email
verification, a full staff-only admin dashboard, and an **Agentic AI Admin
Copilot** (8 autonomous agents + live chat, Groq-backed) with its own
**automated evaluation framework** that grades the copilot's real behavior.

Git repo root is this directory (`backend/` and `frontend/` are siblings
here, not nested repos). Remote: `github.com/Alihaiderk689/Smart-Task-Productivity-Manager`.

## Dev environment

```bash
# Backend -- venv lives at backend/.venv (not top-level, not system python)
cd backend && source .venv/bin/activate
python manage.py runserver 8000

# Frontend
cd frontend && npm run dev          # http://localhost:5173

# Celery worker + Beat (needed for reminder emails AND every copilot agent's
# scheduled sweep -- see config/celery.py's beat_schedule)
cd backend && source .venv/bin/activate
celery -A config worker -B --loglevel=info

# Redis must be running independently (Celery's broker)
```

Secrets live in `backend/.env` (gitignored) — `GROQ_API_KEY` for the
copilot's LLM calls (`GEMINI_API_KEY` / `OPENROUTER_API_KEY` optionally too,
see below), DB/email/Cloudinary credentials. Never echo this file's
contents verbatim in chat.

## Testing

```bash
cd backend && source .venv/bin/activate
python -m pytest                    # 439 tests as of this session
```

Conventions already established in this codebase — follow them, don't
introduce new ones:
- **One `test_<app>.py` per app**, at the app's root (not a `tests/` package).
- Shared fixtures in root `conftest.py`: `api_client`, `test_user`,
  `auth_client`, `other_user`, `staff_user`, `staff_client`,
  `category_factory`, `task_factory`.
- `conftest.py` has two important **autouse** fixtures that make tests
  hermetic — don't remove them:
  - `_use_local_file_storage` — forces local disk instead of real Cloudinary.
  - `_no_real_llm_key` — forces `settings.GROQ_API_KEY = ""`,
    `settings.GEMINI_API_KEY = ""`, and `settings.OPENROUTER_API_KEY = ""`
    for every test by default, even though real keys may live in `.env`,
    so a test that forgets to mock the LLM fails loudly instead of
    silently making a real (billed, network-dependent) call to any of the
    three. Tests that specifically want the "configured" path set the
    relevant `settings.*` back explicitly within the test.

## Backend app map

```
users/         auth: JWT, Google OAuth, OTP email verification, profile, avatar
tasks/         Task model + lifecycle (start/pause/resume/stop/complete/reschedule)
categories/    per-user task tags
dashboard/     aggregate/summary read endpoints
analytics/     productivity score, weekly/monthly stats
notifications/ Celery tasks + email sending (reminders, OTP, etc.)
core/          shared infra checks (core/system_checks.py — DB/Redis/Celery health)
adminpanel/    staff-only oversight: users, tasks, stats, CSV export
copilot/       the Agentic AI Admin Copilot (see below)
evaluation/    automated evaluation harness for the copilot (see below)
```

Frontend mirrors the role split: `Layout.jsx` + `src/pages/*` for regular
users, `AdminLayout.jsx` + `src/pages/Admin*.jsx` for staff — enforced by
`RoleRoute`, so a staff account only ever reaches `/admin/*` and a regular
account never does.

## The Agentic AI Admin Copilot (`copilot` app)

Architecture (built incrementally, "foundation first"):
- `tools/base.py` — `BaseTool` (name, description, JSON-schema `input_schema`,
  `permission` — `None` = safe, `"sensitive"` = mutates data and can only run
  via an approved `Recommendation`). `tools/registry.py` holds the one
  process-wide `tool_registry`, populated in `apps.py::ready()`.
- `agents/base.py` — `BaseAgent`, the Observe → Reason → Plan → Execute →
  Verify → Report loop every agent implements. `execute()` isolates a
  per-tool exception into a failed `ToolResult` instead of aborting the
  whole plan.
- `llm/client.py` — `GroqClient`, thin wrapper over the Groq chat-completions
  API. `llm/gemini_client.py` — `GeminiClient`, and `llm/openrouter_client.py`
  — `OpenRouterClient`, identically-shaped wrappers over Google's Gemini API
  and OpenRouter respectively (both expose an OpenAI-compatible endpoint, so
  both reuse the `openai` package pointed at the provider's own base_url).
  `llm/fallback_client.py` — `LLMClient`, the single entry point both chat
  services and every agent actually use: tries Groq first (with its own
  per-minute-rate-limit retry/backoff), then Gemini, then OpenRouter, each
  only consulted if configured and only after the previous one's retries
  are exhausted. `GEMINI_API_KEY` / `GEMINI_MODEL` (defaults to
  `gemini-flash-latest`) and `OPENROUTER_API_KEY` / `OPENROUTER_MODEL`
  (defaults to `openai/gpt-4o-mini`) are both optional — leave either or
  both blank and the chain just stops earlier (Groq-only if neither is
  set, exactly as before). Every LLM call must check `is_configured` first
  and have a deterministic fallback — nothing in this app may hard-crash
  for lack of a key.
- `models.py` — `AgentRun`, `ToolCallLog`, `ConversationMessage`, `Recommendation`.
- **8 agents** in `agents/`: `system_health`, `analytics`, `user_monitoring`,
  `task_intelligence`, `reminder`, `database_intelligence`, `recommendation`
  (the meta/digest agent), `action` (executes approved recommendations —
  never decides anything on its own, just replays `action_payload`).
- **Chat** — `services/chat_service.py`, live at `/admin/copilot`. Real Groq
  function-calling over the non-sensitive tools only. It has **no path to a
  destructive action**: sensitive tools are excluded from its tool schema,
  and the only way it can cause a mutation is calling `propose_action`
  (`tools/action_tools.py`), which creates a pending `Recommendation` for a
  human to separately approve — the system prompt lists sensitive tool
  names/schemas explicitly so the model doesn't have to guess them.
- **Approval workflow** — `POST /api/copilot/recommendations/<id>/approve|reject/`.
  Approving executes immediately via `ActionAgent` scoped to just that one
  recommendation; a Celery Beat sweep (`run_action_agent_sweep`) catches
  anything approved but not yet executed.
- **Sensitive (approval-gated) tools**: `deactivate_user`, `send_reminder`,
  `delete_completed_tasks`.

## The Evaluation Framework (`evaluation` app)

An automated harness that grades the copilot's *actual* behavior, not just
whether it runs. `POST /api/evaluation/run/` (admin-only, synchronous, real
Groq calls, takes ~20–90s) executes **22 scenarios** across 9 categories
(task visibility, analytics, user management, reminders, task maintenance,
system maintenance, permission boundaries, failure injection, end-to-end
workflows) — see `evaluation/runner.py`. Computes 8 metrics (Task Success
Rate, Tool Selection/Planning/Permission Accuracy, Error Recovery Rate,
Hallucination Rate, Avg Response Time, Workflow Completion Rate) in
`evaluation/metrics.py`. Dashboard at `/admin/evaluation`.

`evaluation/fixtures.py` creates ephemeral users/tasks/categories for
workflow scenarios and tears them down afterward — it runs against the
**real** database, not a throwaway test DB, so:
- Fixture emails are always prefixed `eval-fixture-` and task titles
  `[EVAL]` — if you ever see those in real data, they're leftovers from an
  interrupted run; safe to delete.
- Cleanup also sweeps any `Recommendation` whose `action_payload` merely
  *references* a fixture user/task id, even if the scenario that created it
  never explicitly tracked it (a different agent can legitimately observe
  fixture data mid-run and raise its own recommendation about it).
- Any scenario that approves a destructive action first verifies the
  recommendation's `action_payload` is scoped to a fixture object it
  created itself — it will never blindly approve/execute the first
  matching pending recommendation.

## Gotchas learned the hard way this session

- **`rest_framework.test.APIClient` outside pytest** (e.g. `evaluation/runner.py`,
  invoked from a live, already-running admin-triggered endpoint) needs an
  explicit `HTTP_HOST` override. Under pytest, `setup_test_environment()`
  appends `"testserver"` to `ALLOWED_HOSTS` automatically; outside pytest
  nothing does that, so the default Host header 400s on `DisallowedHost`
  before a view ever runs. See `evaluation/runner.py::_api_client()` for the
  fix (detects which context it's in via `"testserver" in settings.ALLOWED_HOSTS`).
- **Groq free-tier has a *daily* token quota**, not just per-minute — heavy
  session-long testing can exhaust it (`429 ... tokens per day (TPD)`). The
  system degrades gracefully when this happens (verified live), but
  chat-dependent eval scenarios will fail until the quota resets.
- **`BaseTool.run()` must never raise** (contract documented in
  `tools/base.py`) — `BaseAgent.execute()` and `ChatService._run_tool()`
  both defensively catch anyway in case an implementation slips, but new
  tools should still catch their own exceptions and return
  `ToolResult(success=False, ...)`.
- **`Recommendation.action_payload` is a plain JSON blob**, no FK/cascade to
  the user/task it references — deleting the referenced object leaves an
  orphaned recommendation behind unless something explicitly cleans it up.
  Never approve/execute one without confirming what it actually points at.
- The Python venv is **3.9** — `str | None` union syntax needs
  `from __future__ import annotations` at the top of the file; `list[str]` /
  `dict[str, int]` generics work natively (PEP 585) without it.

## Admin test account

`bholarecord699@gmail.com` is a staff/admin account used throughout manual
verification (password known to the user — not recorded here).
