---
name: notifications-reminders
description: Reminders are DATABASE-backed (Reminder model + claim/send sweep), not Celery apply_async — because Render/Vercel free tier can't run persistent Celery workers. Also covers OTP/transactional email via Brevo.
app: notifications
updated: 2026-08-28
---

## What it does

Two things: (1) the reminder scheduling/delivery system for tasks, (2)
transactional email sending (OTP codes, password reset, reminders) via
Brevo's HTTP API.

## Key files

- `backend/notifications/reminder_processor.py` — **the whole reminder
  system**; its module docstring is the canonical explanation, read it
  before touching anything here.
- `backend/notifications/models.py` — `Reminder` model (`Kind`, `Status`
  enums: `PENDING`/`PROCESSING`/`SENT`/`FAILED`/`CANCELLED`).
- `backend/notifications/services.py` — `NotificationService.schedule_reminders(task)`,
  the entry point every task-creating/editing view calls.
- `backend/notifications/email_service.py`, `brevo_backend.py` — the
  actual send path (`EmailService.send_email` → Django `send_mail` →
  `BrevoEmailBackend` → Brevo HTTP API, not SMTP).
- `backend/notifications/tasks.py` — thin Celery wrappers around the same
  functions, used only in local dev via Celery Beat.

## Architecture: why database-backed, not Celery `apply_async(eta=...)`

**Never suggest "just run Celery Beat" as the fix for reminders not
firing, in dev or prod.** This was deliberately replaced: the old
per-task `apply_async(eta=...)` scheduling silently never fired in
production because Render/Vercel's free tiers don't run a persistent
Celery worker + Beat process (see `.env.render`).

Now: `Reminder` rows are written to Postgres at task create/edit time
(one row per offset — 30-min, 5-min, 40%-progress, overdue — only if that
offset is still in the future). A periodic **sweep**
(`process_due_reminders()`) claims and sends whatever's due. In
production, a GitHub Actions cron hits
`core/views.py::run_scheduled_tasks` (see
[core-infra.md](core-infra.md)) to run the sweep — no Redis/Celery
involved in prod at all. Locally, Celery Beat can run the same function
as a convenience, but nothing requires it.

**Delivery guarantee is AT-LEAST-ONCE, not exactly-once — deliberately.**
An occasional duplicate reminder email is an acceptable minor annoyance; a
silently-lost reminder is the actual failure mode this system exists to
prevent. Mechanics: `select_for_update(skip_locked=True)` claims a batch
into `PROCESSING`; a `STALE_LEASE` of 10 minutes lets a later sweep
reclaim a row whose claimant died mid-send (logged loudly, not silent);
the `SENT` transition is written as the very next statement after
`send_email()` returns, minimizing the crash window to microseconds.

**`reminder_version`** (on `Task`, bumped on every reschedule) is how
stale reminders self-invalidate: `_claim_batch` only claims rows where
`generation == task.reminder_version`, so old-generation rows just sit
there inert rather than needing to be deleted. See
[tasks.md](tasks.md)'s "Critical invariant" section — any new code path
that changes a task's schedule must bump this and regenerate.

## If reminders "aren't arriving" locally

Nothing plays the GitHub Actions role automatically in local dev. Check
`Reminder` rows for the task first (status, `scheduled_for`) before
assuming email config is broken — the row tells you whether it was ever
swept at all. Either run `process_due_reminders()` in a Django shell, hit
`run_scheduled_tasks` with the internal key, or run
`celery -A config worker -B` per [CLAUDE.md](../../CLAUDE.md)'s dev
commands.

## Manual/forced sends

`send_reminder_now(task_id, reminder_version, kind)` — used by
adminpanel's trigger-reminder button and the copilot's approval-gated
`send_reminder` tool. Goes through the *same* atomic claim as the sweep,
so a manual trigger and the sweep can never both send the same reminder.

## Touches / related

[tasks.md](tasks.md) (reminder-invalidation invariant),
[core-infra.md](core-infra.md) (the scheduled-tasks endpoint that drives
the sweep in prod), [adminpanel.md](adminpanel.md) /
[copilot-admin.md](copilot-admin.md) (manual trigger surfaces).
