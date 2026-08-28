---
name: tasks
description: Task model + full lifecycle (start/pause/resume/stop/reschedule), repeat series, and the reminder-invalidation rules every schedule-changing endpoint must follow.
app: tasks
updated: 2026-08-28
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

## Endpoints (`backend/tasks/urls.py`, mounted under `/api/tasks/`)

`""` (list/create), `repeat/` (batch create a series),
`<id>/`, `<id>/start/`, `<id>/pause/`, `<id>/resume/`, `<id>/stop/`,
`<id>/reschedule/`.

## Lifecycle rules (`views.py`)

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
