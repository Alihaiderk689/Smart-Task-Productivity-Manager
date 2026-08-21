# SCALABILITY.md

What actually breaks first as usage grows, and why — not a generic
scaling playbook. For the reasoning behind the current shape of the
system, see [ARCHITECTURE.md](ARCHITECTURE.md); for what's insecure at
scale, see [SECURITY.md](SECURITY.md). Every item below is tied to a real
file/behavior in this codebase, not a hypothetical.

## What this is built for today

A single Render free-tier web service, a single Supabase Postgres
instance, and GitHub Actions cron standing in for Celery Beat (see
[ARCHITECTURE.md#background-jobs](ARCHITECTURE.md#background-jobs)).
That's a deliberate low-cost starting point, not an oversight — it's
fine for the current low-hundreds-of-users scale. Everything below is
about what to revisit, and in what order, as that changes.

## What already scales fine (don't "fix" these preemptively)

- **Stateless JWT auth** — no server-side session for the API itself
  (see [ARCHITECTURE.md](ARCHITECTURE.md#authentication-architecture)),
  so adding a second backend instance later needs no sticky sessions or
  shared session store.
- **The reminder claim mechanism already handles concurrent workers
  correctly** — `_claim_batch` in `notifications/reminder_processor.py`
  uses `select_for_update(skip_locked=True)`, so if this ever runs from
  multiple GitHub Actions runs overlapping, or a future dedicated worker
  process, two processes can't double-claim the same `Reminder` row.
  This was already built for horizontal scaling; nothing to change here
  when a worker gets added.
- **Outbound email is a plain HTTP API call, not SMTP** —
  `notifications/brevo_backend.py` sends through Brevo's transactional
  email API. This isn't a scale concern at all today (one HTTP POST per
  email, no persistent connection to manage), but see the Brevo item
  below for the one thing worth watching as volume grows.
- **User data isolation is per-row (`user` FK), not per-schema/per-DB** —
  fine at this scale, and simpler to reason about than tenant-per-schema.
  Revisit only if a genuinely different failure-isolation requirement
  shows up (e.g. one customer's data volume/query pattern degrading
  everyone else's), not as a default "best practice" migration.

## Current bottlenecks, in the order they'll actually bite

### 1. No pagination on user-facing list endpoints

`TaskListCreateView` (`tasks/views.py`) and the equivalent categories
view have no `pagination_class` — confirmed by grep, the only place
`pagination_class` is set anywhere in the codebase is
`adminpanel/pagination.py`'s `AdminListPagination`, used only by the
staff-only admin list views. A regular user's `GET /api/tasks/` returns
every task they've ever created, in one response, every time the
frontend loads the list. Fine at dozens of tasks; a power user with a
few thousand historical tasks (this app supports daily repeating tasks —
see `create_repeating_tasks` — so that accumulates faster than it looks)
will eventually feel this as a slow list view and a growing response
payload. Fix: add `pagination_class` (or at least a default
`DEFAULT_PAGINATION_CLASS` in `REST_FRAMEWORK` settings) once task counts
per user start climbing — not urgent today, but the cheapest of these
fixes and worth doing before it's actually painful.

### 2. Reminder timing has a hard latency floor from the cron cadence, not the code

`notifications/reminder_processor.py` itself is fine under load — it's
pure DB queries + one Brevo API call per due reminder, no LLM calls,
cheap to run often. The floor is `.github/workflows/scheduled-tasks.yml`'s
`*/5 * * * *` cadence for the reminders group (`*/15 * * * *` for the
general system-health/action-agent sweep, `0 9 * * *` for the once-daily
group), plus Render free tier's 70-110s cold start if the service has
idled. In the worst case (reminder becomes due right after a sweep,
service just went idle) a reminder can go out several minutes later than
scheduled. This doesn't get worse with more *users* —
`process_due_reminders(batch_size=200)` processes a whole batch per
sweep — but it does mean the product can never promise sub-5-minute
reminder precision without moving off the free-tier cron-substitute
model (a real always-on worker, or a paid Render instance that doesn't
cold-start).

### 3. Brevo's free-tier daily send cap

Brevo's free plan caps outbound transactional email at 300/day (as of
this writing — confirm the current number in your account's plan page,
these limits change). Every OTP, password reset, and reminder email
counts against it. Not a problem at today's scale, but unlike the
per-request-cheap DB/compute bottlenecks above, this one fails
*abruptly* at the cap rather than degrading gracefully — the app reports
the failure honestly (`BrevoAPIError` propagates through the same
transient-retry path as any other send failure — see
`EMAIL_TRANSIENT_ERRORS` in `notifications/reminder_processor.py`), but
a user hitting "forgot password" on the 301st email of the day still
gets no email, with no in-app signal that this is a *volume* cap rather
than a real error worth debugging. Worth monitoring send volume (Brevo's
own dashboard shows this) and upgrading the plan before growth makes
this a support-ticket generator.

## Not yet a bottleneck, but worth knowing about

- **Render's outbound IP is not static.** Confirmed while wiring up
  Brevo: it enforces an "authorized IPs" allowlist by default on newer
  accounts, which this project's Brevo account has deactivated entirely
  (Settings → Security → Authorized IPs → "Deactivate for API keys")
  rather than trying to keep a Render IP allowlisted, since Render can
  change it between deploys/restarts. If that setting is ever
  re-enabled, email sending will start failing intermittently in
  production with no code change to explain why — check that setting
  first if emails mysteriously stop working after previously working
  fine.
