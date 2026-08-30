---
name: adminpanel
description: Staff-only oversight — user/task management across all accounts, CSV export, manual reminder triggers. IsAdminUser-gated throughout.
app: adminpanel
updated: 2026-08-30
---

## What it does

The staff dashboard's backend: cross-user visibility and management that
regular users never get (regular endpoints in `tasks`/`categories`/etc.
are always scoped to `request.user`; this app is the deliberate
exception, gated by `IsAdminUser` on every view).

## Key files

- `backend/adminpanel/views.py` — all endpoints.
- `backend/adminpanel/serializers.py` — `AdminUserSerializer`/
  `AdminUserDetailSerializer`, `AdminTaskSerializer`/
  `AdminTaskWriteSerializer` (cross-user, unlike the regular `tasks`/
  `users` serializers).
- `backend/adminpanel/pagination.py` — `AdminListPagination`.

## Endpoints (`backend/adminpanel/urls.py`, mounted under `/api/admin/`)

- `overview/`, `system-status/` — dashboard aggregates (`admin_overview`
  reads user counts/growth; `system_status` wraps
  `core.system_checks.get_system_status()` — the fuller DB/Redis/Celery
  check `core.views.health` deliberately skips).
- `users/`, `users/<id>/`, `users/<id>/tasks/` — list/detail/cross-user
  task view.
- `users/<id>/deactivate|activate|delete/` — account lifecycle actions.
- `categories/names/` — `distinct_category_names`: **distinct name
  strings across every user**, not individual `Category` rows (avoids a
  hundred-plus near-duplicate "Work"/"Study"/etc. entries in the admin
  task filter dropdown — see [categories.md](categories.md)).
- `tasks/`, `tasks/<id>/`, `tasks/<task_id>/trigger-reminder/` —
  cross-user task management; the trigger-reminder action calls straight
  into `notifications.tasks`' four per-kind wrappers (see
  [notifications-reminders.md](notifications-reminders.md)).
- `reports/users.csv`, `reports/tasks.csv` — CSV export.

## Invariants / gotchas

- `_overdue_queryset()` (`end_time__lt=now`, excluding `Completed`/
  `Stopped`) is the admin panel's own definition of "overdue" — kept
  local to this file rather than shared with `notifications`' overdue
  reminder logic; if the two drift, admin-panel counts and actual overdue
  emails can disagree. Check both if you're chasing a mismatch.
- `deactivate_user`/`delete_user` here are the **direct, immediate**
  staff-initiated actions — distinct from the copilot's approval-gated
  `deactivate_user` *tool* in [copilot-admin.md](copilot-admin.md), which
  goes through a `Recommendation` first. Same underlying effect, two
  different trigger paths; don't conflate them when debugging "why was
  this user deactivated."
- This file's self-target guard (`target.id == request.user.id` →
  rejected) is now mirrored on the copilot side too — see
  [copilot-admin.md](copilot-admin.md)'s "Server-side authorization
  hardening" section. Keep the two in sync if either guard changes.

## Touches / related

[auth-users.md](auth-users.md) (acts on `User`), [tasks.md](tasks.md),
[categories.md](categories.md), [notifications-reminders.md](notifications-reminders.md)
(manual trigger), [copilot-admin.md](copilot-admin.md) (parallel
LLM-driven path to some of the same actions).
