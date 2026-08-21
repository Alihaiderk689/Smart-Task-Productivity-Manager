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
- **User data isolation is per-row (`user` FK), not per-schema/per-DB** —
  fine at this scale, and simpler to reason about than tenant-per-schema.
  Revisit only if a genuinely different failure-isolation requirement
  shows up (e.g. one customer's data volume/query pattern degrading
  everyone else's), not as a default "best practice" migration.

## Current bottlenecks, in the order they'll actually bite

### 1. ~~Outbound email is on a personal Gmail SMTP relay~~ — fixed, now on Resend's HTTP API

Previously `EMAIL_BACKEND` pointed at `smtp.gmail.com` with a personal
account, which was already failing in production: Gmail actively drops
the STARTTLS handshake for connections from datacenter IPs (Render's, in
this case), and separately, Render blocks outbound SMTP ports (25/465/587)
entirely on its free tier — confirmed directly from production logs
(`smtplib.SMTPServerDisconnected: please run connect() first`, raised
inside `starttls()` → `ehlo()` → `send()`).

Fixed by swapping `EMAIL_BACKEND` to `notifications.resend_backend.
ResendEmailBackend`, which sends through the Resend HTTP API (plain
HTTPS, unaffected by either problem above) instead of raw SMTP.
`notifications/email_service.py` and every call site are unchanged —
they still call Django's standard `send_mail`, which now just routes
through the new backend. Config is now a single `RESEND_API_KEY` env var
instead of `EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/
`EMAIL_USE_TLS`. The one remaining hard requirement, unchanged by this
fix: **a verified sending domain.** Resend's own no-domain/test sender
only delivers to the account owner's own email — it can't send OTPs to
real end users without a domain verified via DNS (SPF/DKIM) in the
Resend dashboard, and `DEFAULT_FROM_EMAIL` must be an address on that
domain.

### 2. No pagination on user-facing list endpoints

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

### 3. Reminder timing has a hard latency floor from the cron cadence, not the code

`notifications/reminder_processor.py` itself is fine under load — it's
pure DB queries + one Resend API call per due reminder, no LLM calls, cheap to
run often. The floor is `.github/workflows/scheduled-tasks.yml`'s `*/5 * * * *`
cadence for the reminders group, plus Render free tier's 70-110s cold
start if the service has idled. In the worst case (reminder becomes due
right after a sweep, service just went idle) a reminder can go out
several minutes later than scheduled. This doesn't get worse with more
*users* — `process_due_reminders(batch_size=200)` processes a whole
batch per sweep — but it does mean the product can never promise
sub-5-minute reminder precision without moving off the free-tier
cron-substitute model (a real always-on worker, or a paid Render
instance that doesn't cold-start).

### 4. Single Render instance — no horizontal scaling, one cold start away from a slow response

Free tier is one instance; there's no load balancer or second instance
to fail over to, and it spins down after inactivity (`.github/workflows/scheduled-tasks.yml`'s
own comments document the 70-110s cold-start figure it works around).
This is a request-latency problem before it's a capacity problem — the
first user to hit the app after a period of idleness eats the cold
start. Moving to a paid Render tier (always-on, and eventually multiple
instances) is the fix, gated purely by when idle-cold-start latency
becomes unacceptable to real users, not by request volume.

### 5. No caching layer — every read hits Postgres directly

Documented as deliberate in
[ARCHITECTURE.md#caching](ARCHITECTURE.md#caching): no `CACHES` backend,
Redis here is Celery's broker/result store only. Correct call at current
scale — don't add a cache speculatively. Revisit specifically if a
particular view (most likely `dashboard`/`analytics`, which aggregate
across a user's whole task history on every request) shows up as slow
under real traffic, and cache that view's result, not as a blanket
addition.

### 6. Copilot/evaluation features have their own, separate scaling ceiling: LLM quota, not traffic

Per [CLAUDE.md](CLAUDE.md)'s gotchas: Groq's free tier has a *daily*
token quota, not just per-minute, and heavy admin usage (chat, the
8-agent sweeps, `evaluation/runner.py`'s 22-scenario harness) can exhaust
it — independent of how many end users the core task-manager product
has. The Gemini/OpenRouter fallback in
`copilot/llm/fallback_client.py` softens this but doesn't remove it.
This scales with *admin* activity, not user count — worth knowing so a
quota exhaustion isn't mistaken for a user-traffic capacity problem.

### 7. `POST /api/evaluation/run/` is synchronous and slow (~20-90s) — fine today only because it's admin-only and throttled to 5/hour

It runs 22 real scenarios with real Groq calls inline in the request/
response cycle, tying up a request-handling slot on a single free-tier
instance for the whole duration. `evaluation_run: 5/hour` throttling
(`config/settings.py`) is what keeps this from being a real problem
today. If this ever needs to run more often, or the admin user base
grows past "just a couple of trusted staff," it should move to a
background job (Celery, once one exists, or `run_scheduled_tasks`'
existing cron-trigger pattern) rather than staying synchronous — not
urgent while it's rare and staff-only.

## Recommended order if you're about to scale up

1. Fix email deliverability (item 1) — this isn't optional-later, it's
   broken now.
2. Add pagination to `tasks`/`categories` list views (item 2) — cheap,
   do it before it's painful rather than after.
3. If reminder precision or cold-start latency starts costing real
   users, move off the free Render tier before anything else on this
   list — items 3 and 4 both trace back to that one constraint.
4. Everything else (caching, evaluation backgrounding, read replicas) —
   only in response to an actual observed bottleneck, not preemptively.
   This codebase already avoids premature infrastructure (see
   [ARCHITECTURE.md#caching](ARCHITECTURE.md#caching)'s explicit
   reasoning) — keep that discipline going forward.
