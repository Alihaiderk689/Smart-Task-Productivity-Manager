# SCALABILITY_AUDIT.md

**Question asked: can this app reliably serve 100 *concurrent* users today?**
Not "100 registered users" (this app already has that, and `SCALABILITY.md`
correctly says low-hundreds-of-total-users is fine) — 100 people hitting
the API in the same window. This is a different, harsher question, and
this document answers it on its own evidence, separate from the existing
`SCALABILITY.md` (which is about *growth over time*, not concurrency).

Audited 2026-08-29. Read-only audit — **no application code was changed**.
Evidence below is a mix of (a) direct code inspection with `file:line`
citations, (b) the existing automated test suite run as-is, and (c) live
concurrency testing against this machine's local stack (seeded with ~59
users / 314 tasks — see prior session), run against configurations that
mirror production as closely as this environment allows.

## Methodology & its limits (read this before the numbers below)

- **Test suite**: `cd backend && python -m pytest -q` — full run, no
  modifications.
- **Live concurrency testing**: a Python `ThreadPoolExecutor`-based
  harness fired 100 concurrent HTTP requests at real, running instances of
  this exact backend, authenticated with real JWTs, against the seeded
  local Postgres database. Two backend configurations were tested:
  1. `gunicorn config.wsgi:application --workers 1` — worst case.
  2. `gunicorn config.wsgi:application --workers 3 --timeout 30` —
     **matches `backend/Dockerfile:25`'s actual `CMD` exactly**, i.e. the
     real production start command as committed to this repo.
- **What this does NOT capture** (material caveats, not disclaimers to
  skip past):
  - **Network latency to the real database.** Local Postgres is on
    `localhost` with sub-millisecond round trips. Production talks to a
    remote Supabase Postgres over the internet. Every query-count finding
    below (e.g. "5 queries instead of 1") will cost **more** in production
    than it measured here, proportional to that RTT — a 5-query endpoint
    that took 20ms locally could easily take 150-300ms+ in production.
  - **This is Django's dev server / a local gunicorn, not Render's actual
    infrastructure.** CPU throttling, shared-tenant noise, and Render
    free tier's real RAM ceiling aren't reproducible here. Numbers below
    should be read as *evidence of mechanism* (what happens when only 3
    workers exist, what happens when two requests race, what happens when
    a rate limit is process-local), not as literal production SLA
    predictions.
  - **100 "concurrent requests from one test client" ≠ "100 distinct
    users."** This matters specifically for IP-scoped rate limits (noted
    inline where it changes the conclusion) — a single-IP burst test will
    trip per-IP throttles that 100 users on 100 different home/mobile IPs
    would not all trip simultaneously.
  - Real, billed LLM calls (Groq/Gemini/OpenRouter) and the 20-90s
    evaluation endpoint were **not** load-tested at concurrency — that
    would burn API quota/cost for a local audit. One single (non-
    concurrent) real chat call was timed for calibration; the blocking-
    time analysis for these paths is evidence-based from code (retry/
    backoff constants, timeout config) rather than from hammering a paid
    API.
- **Race-condition testing**: a barrier-synchronized two-thread script hit
  `POST /api/tasks/<id>/pause/` and `POST /api/tasks/<id>/stop/` on the
  same in-progress task at the same instant, repeated across 5 seeded
  tasks, against the 3-worker instance above.

---

## System topology (established from code, not assumed)

- **Backend**: Django REST Framework, served by **`gunicorn --workers 3`**,
  sync worker class (no `--worker-class`, no `--threads` set) — confirmed
  at `backend/Dockerfile:25`. No `render.yaml`/`Procfile` exists in the
  repo, so this `CMD` is the only in-repo evidence of what actually runs;
  Render's dashboard could override it, but nothing in this repo suggests
  it does.
- **No explicit `--timeout`** is set anywhere → gunicorn's own default
  applies: **30 seconds**, confirmed directly against the installed
  version (`gunicorn.config.Timeout.default == 30`).
- **Single Render free-tier instance.** No autoscaling config exists
  anywhere in this repo. Cold-starts 70-110s after idling (documented in
  `ARCHITECTURE.md:135`, `SCALABILITY.md:68`).
- **No Celery/Redis in production.** Confirmed via `.env.render` (states
  outright that no broker/worker is configured for this deployment),
  `ARCHITECTURE.md:126-135`, and `SCALABILITY.md:11-16`. Scheduled jobs
  run via GitHub Actions cron hitting `core/views.py::run_scheduled_tasks`
  **synchronously in-process**, i.e. inside one of the same 3 gunicorn
  workers.
- **No caching layer of any kind.** Confirmed: no `CACHES` override in
  `config/settings.py` → Django's default `LocMemCache` (per-process, not
  shared). Every read hits Postgres fresh, every time, on every worker.
- **Database**: Supabase Postgres via `DATABASE_URL_PROD`, session-mode
  pooler (port 5432 per `.env.render`), `CONN_MAX_AGE=600` (persistent
  connections). With only 3 workers, this caps at 3 concurrent app-side DB
  connections — under-subscribed today, but see Finding #12.

This topology — **a hard ceiling of 3 simultaneous in-flight HTTP
requests, backend-wide, with no shared cache and no background job
queue** — is the lens every finding below should be read through. A
finding that looks minor in isolation (e.g. "5 queries instead of 1") is
a bigger deal here than in a typical multi-worker/autoscaled deployment,
because there is so little spare capacity to absorb it.

---

## Test suite

```
604 passed, 953 warnings in 96.98s (0:01:36)
```
All green, no failures, no modifications made to reach this result. Good
baseline — none of the findings below are things the existing test suite
was designed to catch (they're concurrency/index/config gaps, not
functional regressions), so this passing doesn't contradict any finding.

---

## Findings

Each finding: evidence, concrete impact, severity. Severity is judged
specifically against "100 concurrent users," not general code quality.

### CRITICAL

**C1 — Hard ceiling of 3 simultaneous requests, backend-wide, and a
single slow one can stall everyone.**
`backend/Dockerfile:25` — `gunicorn ... --workers 3`, sync, no threads.
Live evidence: at 1 worker, 100 concurrent requests to `GET
/api/admin/tasks/` took **2.60s wall-clock, p95=2.43s** to drain, because
every request is served strictly one-at-a-time. At 3 workers (the real
prod config), the same test dropped to **0.93s wall-clock, p95=0.83s** —
confirms near-linear scaling with worker count, i.e. **confirms 3 is a
hard throughput multiplier, not just a config nicety.** Combine this with
C2: any endpoint that blocks a worker for seconds removes a full third of
total backend capacity for the entire app — not just for the user who
triggered it.

**C2 — Copilot chat, admin agent-run, and evaluation-run all run real LLM
calls synchronously inside the request/response cycle, with no queue.**
- `copilot/services/chat_service.py:152` (admin chat) and
  `usercopilot/services/chat_service.py:138` (user chat) call
  `self.llm.chat(...)` synchronously, up to `MAX_TOOL_ROUNDS` times (6 and
  4 respectively — `copilot/services/chat_service.py:64`,
  `usercopilot/services/chat_service.py:24`).
- `copilot/llm/fallback_client.py` retries each of Groq→Gemini→OpenRouter
  up to 3 times with backoff sleeps of `[2, 6]` seconds
  (`fallback_client.py:24,28`) before falling through — worst-case
  realistic blocking time per chat request, all providers configured and
  rate-limited: **~180-450+ seconds** by this math alone.
- **But**: gunicorn's default 30s worker timeout (confirmed above) means
  the worker gets forcibly killed and respawned well before that — so the
  real-world failure mode is **not** "hangs for 5 minutes," it's "the
  admin's/user's request dies with a connection reset/502 after ~30s, and
  the worker is unavailable to serve anyone else for that ~30s." Live
  calibration: one real (non-concurrent) chat call via Groq completed in
  **1.74s** — fine on a good day; the failure mode above is what happens
  when Groq is rate-limited or slow, which `CLAUDE.md` itself documents as
  a real, observed occurrence ("Groq free-tier has a *daily* token
  quota").
- `POST /api/evaluation/run/` (`evaluation/views.py:20`) is documented
  (`CLAUDE.md`) as taking **~20-90 seconds**, synchronous, no
  `.delay()`/Celery anywhere in `evaluation/runner.py`. **A meaningful
  fraction of real evaluation runs are already likely hitting gunicorn's
  30s timeout in production today** and failing with a 502 the admin
  triggering it has no reason to expect, given the endpoint's own
  documented normal runtime exceeds the server's own request timeout.
- **Impact at 100 concurrent users**: with only 3 workers total, **2-3
  admins/users simultaneously using chat, running an agent, or running an
  evaluation is enough to stall 100% of the app — task CRUD, login,
  everything — for up to 30 seconds per stuck request**, for every one of
  the other ~97-98 concurrent users. This is the single most severe
  finding in this audit given the app's flagship feature is exactly this
  AI copilot.

**C3 — `run_agent` has no rate limit at all, unlike every sibling
LLM-calling endpoint.**
`copilot/views.py:42-57` (`POST
/api/copilot/agents/<agent_name>/run/`) has no `@throttle_classes`
decorator — confirmed by direct comparison against `chat_send`
(`copilot/views.py:151-153`, throttled) and `trigger_evaluation`
(`evaluation/views.py`, throttled at `5/hour`). Any admin can call this
at unlimited frequency; each call blocks a worker for the same LLM
worst-case window as C2 (one `summarize()` call still goes through the
full 3-provider retry chain). Combined with C1, this is an easy,
unintentional way to self-DoS the whole app.

**C4 — Rate limiting is backed by a per-process in-memory cache, so
every configured limit is silently ~3x looser than it looks — and gets
*worse*, not better, if workers are scaled up.**
No `CACHES` override exists in `config/settings.py` → Django's default
`LocMemCache`, which is **per-process**. With 3 gunicorn workers, each
holds its own independent counter for every throttle scope
(`config/settings.py:320-329`: `auth: 10/min`, `copilot_chat: 20/min`,
`evaluation_run: 5/hour`, etc.).
**Live empirical confirmation**: `AuthRateThrottle` (`users/
throttling.py:4-14`) is configured at `10/min` per IP. A 100-request
concurrent burst at the same IP against the 1-worker instance let through
**8/100** (close to the configured 10). The identical burst against the
**3-worker** (real prod config) instance let through **26/100** — roughly
3x the configured rate, exactly matching "one independent counter per
worker process." This is a real security/abuse-surface regression: the
brute-force protection on login/signup/password-reset is materially
weaker than its own configuration implies, and naively "fixing" C1 by
raising `--workers` further loosens it further.
*(Caveat noted per Methodology: this is a single-IP burst — 100 distinct
users on 100 distinct IPs wouldn't collide on this specific limit the
same way. The finding stands regardless, because a single IP behind NAT/
a shared corporate or campus network, or a credential-stuffing script,
is exactly the scenario this throttle exists to stop, and it's 3x
weaker than intended.)*

**C5 — `auth_user.email` has no database index or uniqueness constraint,
and it's the single hottest lookup column in the app.**
This project uses Django's stock `User` model (no custom
`AUTH_USER_MODEL`), which only indexes/uniques `username` — `email` gets
neither. Every one of these does an unindexed sequential table scan, on
every call:
- `users/views.py:132,140` — every login.
- `users/views.py:192` — every Google login.
- `users/views.py:238,276` — every OTP verify/resend.
- `users/views.py:444` — every password-reset request.
- `users/serializers.py:43` — every signup's uniqueness check.

No migration in `users/migrations/` ever adds an index or `unique=True`
on this column (confirmed by grep). **Severity is Critical specifically
because this is the one finding in the whole audit that scales with
*total registered users*, not per-user data** — every other finding here
gets worse as one user's own data grows; this one gets worse as the
*platform* grows, and it's on the single most-hit code path (nobody uses
this app without logging in first).

**C6 — Task lifecycle transitions have no locking, and this was
reproduced live, not just theorized.**
`start_task`, `pause_task`, `resume_task`, `stop_task`, `reschedule_task`
(`tasks/views.py:73-300`) all follow: `Task.objects.get(...)` → check
`task.status` in Python → `task.save()`. Zero occurrences of
`select_for_update()`, `transaction.atomic`, or a conditional
`.update(status=...)` compare-and-swap anywhere in the file (confirmed by
grep).

**Live reproduction**: a barrier-synchronized concurrent `pause` +
`stop` fired at the same instant on the same in-progress task, repeated
across 5 seeded tasks against the real 3-worker config:

| Task | `pause` response | `stop` response | Final DB state |
|---|---|---|---|
| 384 | 400 (correctly rejected) | 200 Completed | Completed — consistent |
| **300** | **200 Paused** | **200 Completed** | **Paused** — `stop`'s own 200 response lied |
| **251** | **200 Paused** | **200 Completed** | Completed — `pause`'s own 200 response lied |
| 231 | 400 (correctly rejected) | 200 Completed | Completed — consistent |
| **172** | **200 Paused** | **200 Completed** | **Paused** — `stop`'s own 200 response lied |

**3 of 5 trials produced a state where a caller received an HTTP 200
"success" response that does not match what actually got persisted.**
For task 172 specifically: the client that called `stop` was told the
task is now `Completed` with a `completed_at` timestamp — the actual row
is `Paused`, `completed_at=NULL`. A frontend trusting that response body
(reasonable — it's a 200) will show the user a state the database
disagrees with until the next full refetch. At 100 concurrent users, each
with their own devices/tabs/flaky-network retries, double-submission on a
task-lifecycle button is not an edge case — it's routine. *(Test
artifacts were reset back to `Pending` after the run; no lasting data
changes.)*

### HIGH

**H1 — No pagination on the primary task list endpoint.**
`tasks/views.py:24-29` `TaskListCreateView` returns a user's **entire**
task history on every `GET /api/tasks/` — confirmed no `pagination_class`
and no `DEFAULT_PAGINATION_CLASS` set in `REST_FRAMEWORK`
(`config/settings.py:304-330`; only `adminpanel/pagination.py`'s
`AdminListPagination` exists, applied only to 3 staff-only views). Hot
path — hit on every task-list page load, every one of 100 users. Gets
materially worse over time given `create_repeating_tasks` can generate
many rows per series (`tasks/models.py:77-85`).

**H2 — Dashboard and analytics endpoints issue 5-7 separate `.count()`
queries where one aggregate would do.**
- `dashboard/views.py:14-26` `dashboard_summary` — 5 `.count()` calls.
- `analytics/views.py:13-36` `productivity_summary` — 5 `.count()` calls.
- `analytics/views.py:39-63` `weekly_report` — a `for i in range(7)` loop
  issuing one `.count()` per day (7 queries).
- `analytics/views.py:66-97` `monthly_report` — similar loop, ~4-5
  queries.

All are on the app's most-visited pages (dashboard is the landing view).
5-7x query amplification, trivially fixable with `.aggregate()` /
`.values(...).annotate(Count(...))` — `adminpanel/views.py:52-83`
`admin_overview` already demonstrates the correct pattern in this same
codebase.

**H3 — `Task.status`, `start_time`, `end_time`, `completed_at` are
unindexed despite being the most-filtered non-FK columns in the app, and
there is no `(user, status)` composite index despite that being the
dominant query shape** (a user's task list, filtered/grouped by status —
used across `tasks/views.py`, `dashboard/views.py`, `analytics/views.py`,
`adminpanel/views.py`, and both copilot tool sets). Combined with H1
(no pagination, so every request also does an unindexed `ORDER BY
created_at` sort of the *entire* per-user result set — `Meta.ordering =
["-created_at"]`, `tasks/models.py:91`, and `created_at` isn't indexed
either), this is currently masked by low per-user row counts but is a
direct function of exactly the kind of growth `SCALABILITY.md` already
flags (repeat-series tasks). For contrast, `notifications/models.py`'s
`Reminder` model is well-indexed (`Meta.indexes` on `(status,
scheduled_for)` matching its actual query shape exactly) — the pattern
is known and applied elsewhere in this codebase, just not here.

**H4 — No caching layer at all.** Confirmed (see Topology). Every
dashboard/analytics read — the exact endpoints H2 shows are already
5-7x over-queried — hits Postgres fresh on every request from every one
of 100 users, even though this data (a user's own task stats) changes far
less often than a dashboard is refreshed/polled.

**H5 — `process_due_reminders` sends one synchronous Brevo HTTP call per
due reminder, in a loop, with a 15s timeout each** (`notifications/
reminder_processor.py`, confirmed no batching/async). 100 concurrent
users creating tasks (each generating up to 4 reminders) can plausibly
put 100+ reminders due in the same 5-minute sweep window. Worst case (all
individually slow): minutes, tying up 1 of only 3 workers for the
duration and risking the sweep itself exceeding GitHub Actions' cron
timeout.

**H6 — Two more check-then-act races beyond C6, lower likelihood but
real:**
- `users/otp.py:26-55` `issue_otp` — resend-lockout counter
  (`send_count`) is read-then-incremented with no lock. Two near-
  simultaneous "Resend code" taps (plausible on a flaky mobile
  connection) both pass the cooldown check and both send — the counter
  under-counts and the user receives two OTP emails where only the later
  one's code is actually valid, a confusing bug with no server-side
  protection despite the cap existing specifically to prevent this.
- `users/views.py:192-204` `google_login`, new-account branch — no
  `try/except IntegrityError` around `User.objects.create_user(...)`
  (unlike the signup path, which does have this guard). Two concurrent
  clicks of "Continue with Google" for a brand-new account can both pass
  the `user is None` check and both attempt to create the same username —
  the second raises an unhandled `IntegrityError` → 500, not a graceful
  "already exists."
- `copilot/views.py:113-134` `approve_recommendation` — status check
  (`pending`) and the subsequent `ActionAgent` execution are not atomic/
  locked. Double-clicking "Approve" (admin-only, so likelihood scales
  with concurrent *admins*, not the full 100) can execute a sensitive
  tool (`send_reminder`, `deactivate_user`, `delete_completed_tasks`)
  twice.

### MEDIUM

**M1 — Render free tier's real RAM ceiling (512MB, publicly documented
by Render, not asserted anywhere in this repo) is tight for 3 Python/
Django processes plus per-request working memory of H1's unbounded query
results.** No evidence in-repo this has been measured/budgeted.

**M2 — Admin CSV exports (`adminpanel/views.py:270-301`) materialize the
entire result set in memory, unpaginated, in one un-chunked
`HttpResponse`.** Fine at 100 users' worth of data; will not scale much
past that. Low urgency but worth flagging as a ceiling, not just a style
nit.

**M3 — bcrypt cost-12 password hashing (Django's unmodified default,
confirmed via `AUTH_PASSWORD_HASHERS`) is CPU-bound, ~150-300ms per
login/OTP-verify.** Correct choice, but with only 3 sync workers, 100
concurrent logins serialize into ~33 sequential hashing batches —
measurable, if not severe, added latency stacked on top of every other
finding competing for the same 3 slots.

**M4 — Supabase session-mode pooler (port 5432) + `CONN_MAX_AGE=600`
is fine *only because* the worker ceiling (C1) is so low** (max 3
concurrent app-side DB connections today). This is a real prerequisite,
not just a note: if C1 is fixed by naively raising `--workers`/adding
instances without also moving to transaction-mode pooling (port 6543),
this stops being fine.

**M5 — Cold start (70-110s, documented in `ARCHITECTURE.md`) with zero
autoscaling.** If a genuine 100-concurrent-user burst arrives after the
single free-tier instance has idled, the first ~70-110s is a near-total
outage window for all 100 users simultaneously, before the question of
worker-count capacity is even reached.

### LOW / credit — already handled correctly

Worth stating plainly, not just implied by omission — these show the
team already applies the right pattern where it matters, which makes the
gaps above easier to trust as real gaps rather than a systemic skill
issue:

- `notifications/reminder_processor.py` — `select_for_update
  (skip_locked=True)` inside `@transaction.atomic` for reminder claiming.
  Genuinely correct, race-safe design; explicitly built for multiple
  concurrent claimers. **Do not "fix" this — model C6's fix on it.**
- `adminpanel/views.py:183,216,293` — proper `select_related("category",
  "user")` everywhere an FK is touched per-row.
- `adminpanel/views.py:52-83` `admin_overview` — proper `.annotate
  (Count(...))` aggregates, the exact pattern H2 is missing elsewhere.
- `copilot/tools/*.py`, `usercopilot/tools/*.py` — no N+1 patterns found
  anywhere across either tool set; consistent use of aggregate queries.
- `notifications/models.py` `Reminder` — the best-indexed model in the
  codebase, `Meta.indexes` matching its real query shape exactly.
- Stateless JWT auth — no server-side session, so C1's fix (more
  workers/instances) needs no sticky-session work when it happens.
- `AdminUserListView`/`AdminUserTasksListView`/`AdminTaskListView` — the
  three genuinely global admin list views are correctly paginated
  (`adminpanel/pagination.py`).
- `usercopilot/services/chat_service.py`'s `seen_calls` dedup — correctly
  scoped to one request's own retry loop, not a cross-request race;
  verified this is *not* a finding, not just assumed.

---

## Capacity estimate

Two different numbers, because the answer genuinely depends on what those
100 concurrent users are doing — this app's own most-differentiated
feature (the AI copilot) is also its biggest concurrency liability:

| Traffic pattern | Estimated reliable concurrent capacity today |
|---|---|
| **Pure CRUD** (browsing tasks, dashboard, categories — no AI copilot use) | Roughly **40-80** concurrent users before p95 latency and the C4/H1-H4 gaps become clearly felt, based on the 3-worker live benchmark's near-linear queueing behavior plus expected Supabase network RTT not reproducible locally. Degraded (multi-second tails, not fast), not broken — **if** nothing else competes for the 3 workers at the same time. |
| **Realistic mixed traffic** (some fraction of the 100 touch chat/agents/evaluation, as the app's own feature set invites) | **As few as 2-3 concurrent slow AI requests (C2/C3) stall 100% of the app for all 100 users**, each for up to ~30s per stuck request. This is the binding constraint, not raw request volume. |

The honest single number: **this deployment cannot currently guarantee
100 concurrent users reliably**, because the ceiling isn't "how much
traffic can it take" (the CRUD-only number above is not embarrassing for
a free-tier single instance) — it's "how many of those 100 people can be
simultaneously unlucky enough to use the flagship AI feature before
everyone else's experience breaks," and that number is in the single
digits.

---

## Prioritized fix list

Not implemented here (audit only, per scope) — ranked by how directly
each closes the gap between current state and reliable 100-concurrent-
user support. None of these require an architectural rewrite; the
correctly-solved cases above (reminder claiming, JWT statelessness) show
the right patterns already exist in this codebase.

**P0 — blocks reliable 100-concurrent-user support:**
1. Move LLM-calling endpoints (chat, agent-run, evaluation-run) off the
   synchronous request path — background task + polling/webhook, even a
   minimal one, so a slow AI call no longer holds a gunicorn worker
   hostage (C2, C3).
2. Add the missing throttle to `run_agent` (C3) — five-minute fix,
   mirrors the pattern already used on its sibling endpoints.
3. Move rate-limit storage to a shared backend (Redis is already
   provisioned for Celery in this stack) so throttle counts are accurate
   across all workers (C4).
4. Add an index (or a normalized lowercase-email column with a proper
   unique index) on `auth_user.email` (C5) — the highest-leverage single
   migration in this list given it's on every auth request.
5. Wrap task lifecycle transitions in `select_for_update()` +
   `transaction.atomic()`, or switch to a conditional `.update(status=
   expected_status, ...)` compare-and-swap (C6) — directly reproduced,
   not theoretical.
6. Increase worker/thread capacity beyond 3 sync workers (a paid Render
   tier, `--worker-class gthread --threads N`, or both) — but only
   together with #7, since C1's low worker count is currently the only
   thing keeping M4's DB-connection math safe.

**P1 — needed well before general availability at this scale:**
7. Move to Supabase's transaction-mode pooler (port 6543) before/alongside
   any worker-count increase (M4).
8. Add pagination to `TaskListCreateView` and `CategoryListCreateView`
   (H1) — cheapest fix in this entire list, `SCALABILITY.md` already
   flagged it independently.
9. Replace the 5-7 sequential `.count()` calls in dashboard/analytics
   with single aggregate queries (H2) — `adminpanel/views.py`'s
   `admin_overview` already shows the pattern to copy.
10. Add `(user, status)` and `(user, start_time)`/`(user, end_time)`
    composite indexes on `Task` (H3).
11. Add a real cache layer (Redis, already available) for read-heavy,
    slow-changing aggregate endpoints (H4).
12. Wrap `issue_otp`'s send-count check in a lock/atomic update, and add
    the missing `try/except IntegrityError` to `google_login`'s
    account-creation branch to match `signup`'s existing guard (H6).
13. Batch or backgrounds `process_due_reminders`'s per-reminder Brevo
    calls so one slow sweep can't monopolize a worker (H5).

**P2 — worth doing, not blocking:**
14. Measure actual production RAM headroom under load rather than
    assuming Render free tier's 512MB is sufficient for 3 workers plus
    H1's unbounded payloads (M1).
15. Paginate/stream the admin CSV export endpoints (M2).
16. Budget for cold-start/no-autoscaling explicitly if a genuine traffic
    burst is a realistic scenario for this product (M5) — a different
    kind of fix (infra tier, not code).

---

## Verdict

**Not Ready for 100 users.**

Not because the codebase is poorly built — the correctly-solved cases
(reminder claiming's `select_for_update`, stateless JWT, several
well-indexed/well-aggregated admin and copilot-tool paths) show real
concurrency awareness already exists here. It's not ready specifically
because of a small, concrete, fixable set of gaps: a 3-worker hard
ceiling shared unprotected with synchronous multi-minute-capable LLM
calls (empirically the most severe finding), a rate-limiter that's
quietly 3x weaker than configured, one missing index on the single
hottest column in the app, and a task-lifecycle race this audit didn't
just predict but reproduced live. Every item above is additive —
indexes, pagination, an atomic transaction, a throttle backend swap, and
moving a handful of endpoints off the request path — not a redesign.
