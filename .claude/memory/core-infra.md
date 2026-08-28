---
name: core-infra
description: Health check + the run_scheduled_tasks endpoint that substitutes for Celery Beat in production (Render free tier has no worker process).
app: core
updated: 2026-08-28
---

## What it does

Shared infra: a public health probe, DB/Redis/Celery system-status checks,
and — the important one — `run_scheduled_tasks`, the endpoint that plays
Celery Beat's role in production.

## Key files

- `backend/core/views.py` — `health`, `run_scheduled_tasks`.
- `backend/core/system_checks.py` — `check_database()`,
  `get_system_status()` (fuller DB/Redis/Celery check, used by
  [adminpanel.md](adminpanel.md)'s overview, not by `health`).
- `.github/workflows/scheduled-tasks.yml` — the actual cron caller (repo
  root, not under `backend/`).

## Why this exists

Render's free tier runs no persistent Celery worker/Beat (a second
always-on dyno costs money). `config/celery.py`'s `beat_schedule` is
still the source of truth for *what* runs and *how often* in Docker
Compose / local dev; in production, `scheduled-tasks.yml`'s cron
independently mirrors that cadence and POSTs to `run_scheduled_tasks`
instead. Each job function is called **directly, synchronously,
in-process** (`task_fn()`, not `.delay()`/`.apply_async()`) — there's no
broker to hand off to.

**Consequence for anyone changing `beat_schedule`**: a new entry there
does nothing in production until `scheduled-tasks.yml`'s cron list *and*
one of `JOB_GROUPS`'s three dicts (`_frequent_jobs`, `_daily_jobs`,
`_reminder_jobs`) are updated to match. The two are not linked
automatically — this is the single easiest thing to forget when adding a
new periodic job.

## The three job groups

- **`frequent`** (`*/15 * * * *`): `run_system_health_check`,
  `run_reminder_check`, `run_action_agent_sweep` — cheap, includes
  copilot/LLM work.
- **`reminders`**: `process_due_reminders` — its own faster cadence,
  separate from `frequent` specifically because the app's 5-minute-before
  reminder can't be served by a 15-minute sweep, and this job is pure DB +
  SMTP (no LLM calls), so it stays cheap enough to run that often. See
  [notifications-reminders.md](notifications-reminders.md).
- **`daily`** (`0 9 * * *`): `send_daily_progress_reminders` plus the five
  daily copilot agent checks (analytics, user monitoring, task
  intelligence, database intelligence, recommendation digest).

## Auth & response contract

- `run_scheduled_tasks` is authenticated by a shared secret
  (`X-Internal-Task-Key` header vs. `settings.INTERNAL_TASK_KEY`), not a
  user JWT — the only caller is the GitHub Actions workflow. **Any auth
  failure returns 404, not 401/403** — deliberate, so the endpoint's
  existence isn't revealed to scanners.
- Per-job failures are isolated (one flaky job never stops the rest of
  the group). Response status reflects the aggregate: `200` all ok,
  `500` all failed (systemic — DB down, bad deploy), `207` mixed. The
  workflow checks the body's `success` field rather than trusting HTTP
  status alone, since `curl --fail` treats `207` as success.
- `health` is deliberately public (`AllowAny`) and checks **only** the
  database — the workflow polls it first to wake a sleeping Render
  free-tier instance (70–110s cold start) before attempting a real job
  run, and adding the heavier Redis/Celery checks here would always
  report "down" in this brokerless deployment and just add latency.

## Touches / related

[notifications-reminders.md](notifications-reminders.md) (the
`reminders` job group), [copilot-admin.md](copilot-admin.md) (every
agent's scheduled sweep runs through `frequent`/`daily`).
