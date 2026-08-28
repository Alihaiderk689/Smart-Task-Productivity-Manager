---
name: analytics
description: Productivity score + weekly/monthly completion reports, all computed live from tasks.Task.
app: analytics
updated: 2026-08-28
---

## What it does

Time-based productivity reporting over `tasks.Task`, scoped to
`request.user`. No models of its own, no caching — everything in
`backend/analytics/views.py` is computed per-request.

## Endpoints

- `productivity_summary` — status counts plus `productivity_score =
  round(completed / total * 100, 2)`; `0` (not an error) when the user has
  no tasks yet.
- `weekly_report` — one row per day of the **current** week (Mon–Sun,
  `today - today.weekday()` as the anchor), `completed_tasks` count per
  day keyed off `completed_at__date`.
- `monthly_report` — the current calendar month split into `Week 1..N`
  chunks of up to 7 days (via `calendar.monthrange`), same
  `completed_at__date` counting.

## Invariants / gotchas

- All three reports count by `completed_at`, **not** `start_time` — a
  task completed today that was originally scheduled last week counts
  toward *today's* bucket, not the scheduled day. This is deliberate
  (it's a "what did I actually finish" report) but easy to misread as a
  bug if you're expecting schedule-based grouping.
- `weekly_report`/`monthly_report` are always anchored to "now" — there's
  no date-range parameter to look at a past week/month. If you add one,
  keep the same day-boundary logic (`timezone.localdate()`-based, not
  UTC).
- This is the source the copilot's `analytics_tools.py` / `AnalyticsAgent`
  reads from too — see [copilot-admin.md](copilot-admin.md).

## Touches / related

[tasks.md](tasks.md) (sole data source), [dashboard.md](dashboard.md)
(sibling read-only app, "right now" vs. "over time"),
[copilot-admin.md](copilot-admin.md) (`AnalyticsAgent` wraps this app's
logic for the AI copilot).
