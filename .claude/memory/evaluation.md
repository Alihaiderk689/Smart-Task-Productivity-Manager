---
name: evaluation
description: Automated harness that grades the AI Admin Copilot's real behavior — 22 scenarios, 8 metrics, runs against the live database with prefixed/tagged fixture data.
app: evaluation
updated: 2026-08-28
---

## What it does

Grades `copilot`'s *actual* behavior (not just "does it run") by
executing real scenarios against a real Groq-backed copilot and scoring
the results. Admin-only, synchronous, ~20–90s per run.

## Key files

- `backend/evaluation/runner.py` — orchestrates the 22 scenarios across 9
  categories (task visibility, analytics, user management, reminders,
  task maintenance, system maintenance, permission boundaries, failure
  injection, end-to-end workflows).
- `backend/evaluation/metrics.py` — computes 8 metrics: Task Success
  Rate, Tool Selection Accuracy, Planning Accuracy, Permission Accuracy,
  Error Recovery Rate, Hallucination Rate, Avg Response Time, Workflow
  Completion Rate.
- `backend/evaluation/fixtures.py` — creates and tears down ephemeral
  users/tasks/categories for workflow scenarios.
- `backend/evaluation/views.py` — `POST /api/evaluation/run/`.

## Endpoint

`POST /api/evaluation/run/` — admin-only, synchronous (real Groq calls,
no async job queue), takes ~20–90s. Dashboard at `/admin/evaluation`
(`frontend/src/pages/AdminEvaluation.jsx`).

## Runs against the REAL database — not a throwaway test DB

This is the single most important thing to know before touching this app:

- Fixture emails are always prefixed `eval-fixture-`, task titles
  `[EVAL]`. If you ever see those in real data, they're leftovers from an
  interrupted run — safe to delete.
- Cleanup sweeps any `Recommendation` whose `action_payload` merely
  *references* a fixture user/task id, even if the scenario that created
  the fixture never itself tracked that recommendation — a different
  agent can legitimately observe fixture data mid-run and raise its own
  recommendation about it, and that still needs cleaning up.
- Any scenario that approves a destructive action first **verifies the
  recommendation's `action_payload` is scoped to a fixture object it
  created itself** — it will never blindly approve/execute the first
  matching pending recommendation it finds. If you add a new scenario
  that approves anything, keep this scoping check.

## Gotcha: `APIClient` outside pytest needs an explicit `HTTP_HOST`

`rest_framework.test.APIClient`, used here from a live already-running
admin-triggered endpoint (not under pytest), needs an explicit `HTTP_HOST`
override. Under pytest, `setup_test_environment()` appends `"testserver"`
to `ALLOWED_HOSTS` automatically; outside pytest nothing does that, so the
default Host header 400s on `DisallowedHost` before a view ever runs. See
`evaluation/runner.py::_api_client()` — it detects which context it's in
via `"testserver" in settings.ALLOWED_HOSTS`.

## Other gotchas

- Groq's **daily** token quota (not just per-minute) can be exhausted by
  heavy session-long testing — chat-dependent scenarios will fail until
  it resets. Same caveat as [copilot-admin.md](copilot-admin.md).

## Touches / related

[copilot-admin.md](copilot-admin.md) (the thing being graded — read that
file for the tool/agent/recommendation model this harness exercises).
