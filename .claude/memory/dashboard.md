---
name: dashboard
description: Read-only aggregate/summary endpoints over a user's own tasks — no models of its own.
app: dashboard
updated: 2026-08-28
---

## What it does

Pure read-side aggregation over `tasks.Task`, scoped to `request.user`.
No models, no writes — every view is a plain `@api_view(["GET"])` function
in `backend/dashboard/views.py`.

## Endpoints

- `dashboard_summary` — counts by status (`total`, `pending`,
  `in_progress`, `completed`, `missed`).
- `today_tasks` — tasks with `start_time__date == today` (uses
  `timezone.localdate()`, so this follows Django's configured timezone,
  not UTC-naive "today").
- `upcoming_tasks` — `start_time__gt=now`, ordered ascending.
- `high_priority_tasks` — `priority="High"`, ordered by `start_time`.
- `missed_tasks` — `status="Missed"`, ordered by `-end_time`.

## Invariants / gotchas

- All counts are computed live on every request (no caching layer exists
  anywhere in this project — see `ARCHITECTURE.md`'s Caching section). Fine
  at current scale; don't assume a cache exists if a count looks stale.
- Distinct from [analytics.md](analytics.md): this app is "what's on my
  plate right now," analytics is "how am I doing over time." Don't add
  productivity-score-style logic here — it belongs in `analytics`.

## Touches / related

[tasks.md](tasks.md) (sole data source), [analytics.md](analytics.md)
(sibling read-only aggregation app).
