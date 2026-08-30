---
name: tasks
description: Task model + full lifecycle (start/pause/resume/stop/reschedule), repeat series, and the reminder-invalidation rules every schedule-changing endpoint must follow.
app: tasks
updated: 2026-08-30
---

## What it does

Core `Task` CRUD plus an explicit status lifecycle and multi-day "repeat
series" creation. Per-user, isolated via `get_queryset()` filtering on
`user=self.request.user` everywhere (see `SECURITY.md`'s user-data-
isolation section).

## Key files

- `backend/tasks/models.py` — the `Task` model.
- `backend/tasks/views.py` — `TaskListCreateView`, `TaskDetailView`, and
  the lifecycle actions.
- `backend/tasks/urls.py`, `serializers.py`, `validators.py`,
  `celery_tasks.py`.

## Model shape (`backend/tasks/models.py`)

- `status`: `Pending → In Progress ⇄ Paused → Completed`, plus `Stopped`
  and `Missed` (the latter set only by the overdue reminder path — see
  [notifications-reminders.md](notifications-reminders.md)).
- `priority`: `Low` / `Medium` / `High`.
- Planned schedule: `start_time`/`end_time`. Actual: `started_at`/
  `completed_at`.
- Reminder tracking flags (`reminder_30_sent`, `reminder_5_sent`,
  `reminder_progress_sent`, `reminder_overdue_sent`) and
  `reminder_version` (bumped on every schedule change so stale reminders
  self-invalidate — full mechanism in
  [notifications-reminders.md](notifications-reminders.md)).
- `repeat_group_id` / `repeat_index` / `repeat_total` — set only by
  `create_repeating_tasks`; null for normal single-create tasks. Each day
  of a repeated task is still its own independent `Task` row (a single row
  can't be "done Monday, still pending Tuesday") — these three fields just
  let the frontend group same-series rows into one card.
- `Meta.indexes`: `(user, status)` composite (the dominant query shape
  across dashboard/analytics/adminpanel) plus single-column `start_time`/
  `end_time` (the today/upcoming/missed range-filter and ordering shape).
  Added per SCALABILITY_AUDIT.md's H3 — grep dashboard/views.py and
  analytics/views.py before adding more; don't guess at query patterns.
  **Migration `0013` uses `django.contrib.postgres.operations.AddIndexConcurrently`
  with `atomic = False` on the Migration class** (not plain `AddIndex`) —
  `CREATE INDEX CONCURRENTLY` doesn't take the table-level lock a normal
  `CREATE INDEX` does, which matters since `entrypoint.sh` runs `migrate
  --noinput` on every deploy. `atomic = False` is required (Postgres can't
  run `CONCURRENTLY` inside a transaction) — Django raises a clear
  `NotSupportedError` at migrate time if you forget it, not a silent wrong
  behavior. This project only ever runs on Postgres (dev/test/prod all use
  `dj_database_url`, see `config/settings.py`), so there's no other-backend
  fallback to keep working. Follow this same pattern (not plain `AddIndex`)
  for any future index on a table that gets live writes.

## Endpoints (`backend/tasks/urls.py`, mounted under `/api/tasks/`)

`""` (list/create — paginated, see below), `repeat/` (batch create a
series), `<id>/`, `<id>/start/`, `<id>/pause/`, `<id>/resume/`, `<id>/stop/`,
`<id>/reschedule/`.

## Pagination

`TaskListCreateView` uses `pagination_class = core.pagination.DefaultListPagination`
(`page_size=100`, `max_page_size=500`) — `GET /api/tasks/` returns
`{count, next, previous, results}`, not a bare array. Added because the
endpoint had no ceiling at all (SCALABILITY.md H1).

**Frontend must not just unwrap page 1** — an earlier version of this fix
did exactly that (`.results` from the first response only), which silently
truncated any user past 100 tasks (trivially reached: a single 30-day
repeat series is already 30 rows) across every consumer, since none of
them have load-more UI and all expect "every one of this user's tasks."
The real fix, in `frontend/src/api/base44Client.js`'s `Task.list()`/
`Category.list()`: follow the `next` link (via `services/api.js`'s
`fetchPage(url)`) until exhausted and return the full concatenated array —
each individual request server-side still stays bounded by `page_size`/
`max_page_size`, this just makes as many of them as needed instead of
stopping at page 1. Covered by `frontend/src/api/base44Client.test.js`
(asserts >100-record lists are fully recovered across pages). Verified
live against the real dev server too (130 seeded tasks, 2 pages, all
recovered) — see git history if you need to re-run that check.

## Lifecycle rules (`views.py`)

- `start_task`, `pause_task`, `resume_task`, `stop_task` all wrap their
  read-check-write in `with transaction.atomic():` +
  `Task.objects.select_for_update().get(...)` — fixes a live-reproduced
  race (SCALABILITY_AUDIT.md C6) where concurrent requests on the same task
  could both get a 200 response while only one write actually landed.
  Mirrors `notifications/reminder_processor.py`'s locking pattern.
  `reschedule_task` is **not** locked (out of scope when this was fixed —
  same TOCTOU shape exists there if you're touching it next).
- `start_task`: only from `Pending`.
- `pause_task` / `resume_task`: reject from `Pending` (must start first),
  `Completed`, `Stopped`; idempotent no-op (200, not error) if already in
  the target state.
- `stop_task`: marks `Completed` (there is **no separate "Stopped" action**
  any more — "Stop" and "Complete" used to be different statuses/actions
  but meant the same thing to users, so `stop_task` now does what
  `/complete/` used to do; `Stopped` still exists as a status value but
  nothing currently sets it via this endpoint). Cancels pending reminders.
- `reschedule_task`: validates `start_time` in the future and `end_time` >
  `start_time`, **resets the task back to `Pending`** (clears
  `started_at`/`completed_at`), clears all four reminder-sent flags, bumps
  `reminder_version` and `rescheduled_count`, regenerates reminders.

## Critical invariant: reminder invalidation on schedule change

**Any code path that changes `start_time`/`end_time` must clear the four
`reminder_*_sent` flags, clear `last_daily_reminder_date`, bump
`reminder_version`, and call `NotificationService.schedule_reminders(task)`
again.** There are two separate places this is done today:
- `reschedule_task` (dedicated action — also resets status/timestamps).
- `TaskDetailView.perform_update` (a generic PATCH/PUT that happens to
  change the schedule — deliberately does **not** touch status/
  `started_at`/`completed_at`, only reminders, since a plain edit
  shouldn't restart the task's lifecycle).

A latent bug this fixed: editing a task's time via plain PATCH used to
leave reminders scheduled against the *old* time untouched. If you add a
third way to change `start_time`/`end_time` (e.g. a new bulk-edit
endpoint, a copilot tool), it needs the same treatment or reminders will
silently fire at the wrong time. See
[notifications-reminders.md](notifications-reminders.md) for why
`reminder_version` exists (stale-generation reminders are filtered out by
the sweep, not deleted).

## `create_repeating_tasks`

Validates **every** occurrence (same `TaskSerializer` rules as a normal
create — word limits, gibberish check, category ownership) before saving
any of them — a bad occurrence on day 5 fails the whole batch, no partial
series. `repeat_days` bounded to `REPEAT_MIN_DAYS=2`..`REPEAT_MAX_DAYS=30`.
Each occurrence gets its own reminders scheduled independently.

## Touches / related

[notifications-reminders.md](notifications-reminders.md) (every
create/reschedule schedules reminders), [categories.md](categories.md)
(FK, cascade delete), [dashboard.md](dashboard.md) /
[analytics.md](analytics.md) (read-only aggregates over this model),
[copilot-admin.md](copilot-admin.md) /
[usercopilot.md](usercopilot.md) (`task_tools.py` wraps this model's CRUD
for LLM tool-calling).
