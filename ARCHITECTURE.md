# ARCHITECTURE.md

Why this system is built the way it is, not just how to run it. For
day-to-day dev commands and codebase conventions, see
[CLAUDE.md](CLAUDE.md). For the security model, see
[SECURITY.md](SECURITY.md).

## System shape

```
React / Vite SPA
      │  JWT Bearer auth, fetch/axios
      ▼
Django REST Framework  (config/urls.py routes to each app's views.py)
      │
      ├── App-level views (tasks, categories, dashboard, analytics, users)
      │        │
      │        ▼
      │   Django ORM  ──────────────────────────►  PostgreSQL
      │
      └── copilot / evaluation / usercopilot
               │
               ├── tools/   (BaseTool subclasses — the only things allowed
               │             to touch the DB on the copilot's behalf)
               ├── agents/  (BaseAgent subclasses — Observe→Reason→Plan→
               │             Execute→Verify→Report, call tools)
               └── llm/     (LLMClient — Groq → Gemini → OpenRouter fallback
                              chain, all OpenAI-compatible wrappers)

Celery worker + Beat (or, in production, GitHub Actions cron hitting an
internal endpoint — see Background jobs below) drive reminders and every
copilot agent's scheduled sweep, backed by Redis as broker/result store.
```

Frontend and backend are siblings in one repo (`frontend/`, `backend/`),
not nested repos or a monorepo tool — see [CLAUDE.md](CLAUDE.md).

## Why Django REST Framework + a services/tools layer, not just views→ORM

Most of the app (`tasks`, `categories`, `dashboard`, `analytics`) is plain
DRF: `ViewSet`/`@api_view` → `get_queryset()` → serializer → ORM. No
service layer, because there's no cross-cutting business logic to
justify one — CRUD-shaped apps stay CRUD-shaped.

The **copilot** app is different on purpose: LLM-driven code that mutates
data needs a narrower, auditable surface than "the ORM," so it goes
through `tools/` (each tool declares its own JSON-schema input and a
`permission` — `None` or `"sensitive"`) rather than agents calling the ORM
directly. This is what makes the sensitive-tool gating in
[SECURITY.md](SECURITY.md) enforceable: an agent or the chat LLM literally
cannot execute `deactivate_user` — the tool isn't reachable except via an
approved `Recommendation` replayed by `ActionAgent`. See
[CLAUDE.md](CLAUDE.md)'s copilot section for the full agent/tool map.

## Authentication architecture

JWT (`rest_framework_simplejwt`) end to end — no server-side session for
the API itself (Django sessions are only used by the built-in `/admin/`
site). The split is deliberate: the SPA holds the **access token in
memory only** and every ordinary API call is a Bearer token; the
**refresh token never reaches the SPA's JS at all**, living only in an
`HttpOnly` cookie the browser attaches automatically to
`/api/token/refresh/` and `/api/logout/` (see
[SECURITY.md](SECURITY.md#1-authentication)). This is why CORS (an
explicit origin allowlist, `CORS_ALLOW_CREDENTIALS=True`) rather than
CSRF is the primary cross-origin defense for the Bearer-authenticated
majority of the API — see [SECURITY.md](SECURITY.md#4-csrf) for the
narrower CSRF consideration the cookie-carrying endpoints do introduce.

Three ways to establish identity, all converging on the same JWT issuance:
1. **Email/password + OTP** — signup creates the account inactive-for-login
   until `verify_email_otp` succeeds (`users/otp.py`).
2. **Google OAuth** — `google_login` verifies the ID token server-side,
   then finds-or-creates the local `User` from the verified email.
3. **Password reset** — out-of-band token flow, not itself a login path,
   but ends the same way (fresh credentials → normal `login`).

## Authorization architecture

Two tiers only, no role/permission matrix:
- **Authenticated regular user** — default DRF permission
  (`IsAuthenticated`), scoped to their own rows via `get_queryset()`
  filtering (see [SECURITY.md](SECURITY.md#user-data-isolation)).
- **Staff (`is_staff=True`)** — `IsAdminUser`, gates `adminpanel`,
  `copilot`, `evaluation` entirely.

`usercopilot` sits in between deliberately: authenticated-user-only, but
its tool surface only ever touches the *calling* user's own tasks/
categories — it's the copilot app duplicated at the lower trust tier
rather than the admin copilot with a permission check bolted on, because
the two need genuinely different tool sets (no `deactivate_user`-shaped
tool should ever exist at the user tier, approved or not).

## Database design

Single PostgreSQL database (Supabase-hosted in the current production
deploy, plain `postgres:16-alpine` in Docker Compose / CI). No read
replicas, no sharding — this is a single-tenant-per-row multi-tenant app
(every user's data lives in the same tables, isolated by a `user` FK and
enforced in the ORM layer, not by separate schemas/databases per tenant).

`dj_database_url` parses `DATABASE_URL_DEV` / `DATABASE_URL_PROD` from
env; `ssl_require=True` is forced in production
(`config/settings.py`). A discrete `POSTGRES_*` env var block can
override this entirely (used by Docker Compose / CI) — see the comment in
`config/settings.py` around line 173 before touching that block, since
it's easy to accidentally have both paths active and have the discrete
vars silently win.

The copilot's own tables (`AgentRun`, `ToolCallLog`, `ConversationMessage`,
`Recommendation`) live in the same database as app data, not a separate
audit store — `ToolCallLog` is the durable record of every tool
invocation any agent or the chat LLM has ever made, which is what makes
the evaluation framework's metrics (Tool Selection/Planning/Permission
Accuracy) computable after the fact from `evaluation/metrics.py`.

## Background jobs

Two different mechanisms for the same `celery.py` `beat_schedule`,
depending on deploy target:

- **Docker Compose / self-hosted** (`docker-compose.yml`): real
  `celery_worker` + `celery_beat` containers against Redis, exactly as
  `config/celery.py` defines. This is also what local dev
  (`celery -A config worker -B`) approximates.
- **Render free-tier production**: no worker/beat process at all (a
  second always-on dyno costs money). Instead,
  `.github/workflows/scheduled-tasks.yml` runs on the *same* cron cadence
  Beat would use (`*/15 * * * *` for the frequent group — system health,
  reminders, action-agent sweep; `0 9 * * *` for the daily group — daily
  progress reminders + the five daily copilot checks) and POSTs to
  `core/views.py::run_scheduled_tasks`, gated by `INTERNAL_TASK_KEY`
  (`X-Internal-Task-Key` header). It first pings the public
  `/api/core/health/` endpoint and retries for ~4 minutes, because
  Render's free tier cold-starts in 70-110s after idling.
- Individual per-task reminders (as opposed to the fixed daily sweep) are
  scheduled directly via `apply_async(eta=...)` in
  `notifications/services.py`, not through Beat — Beat is only for the
  fixed recurring jobs listed above.

**Consequence for anyone changing `beat_schedule`**: a new entry there
does nothing in production until `scheduled-tasks.yml`'s cron list and
`run_scheduled_tasks`' group dispatch are updated to match — the two are
not linked automatically.

## External APIs

- **Groq / Gemini / OpenRouter** — `copilot/llm/fallback_client.py`'s
  `LLMClient` tries each in order, only if configured, only after the
  previous one's own retries are exhausted. All three are OpenAI-compatible
  endpoints, which is why Gemini and OpenRouter both reuse the `openai`
  package pointed at a different `base_url` rather than each needing a
  bespoke SDK integration.
- **Google OAuth** (`google.oauth2.id_token`) — ID token verification only,
  no broader Google API scope requested.
- **Cloudinary** — user avatar storage, optional
  (`DEFAULT_FILE_STORAGE` only switches to Cloudinary if all three
  `CLOUDINARY_STORAGE` values are set; otherwise local disk, which is what
  keeps fresh dev setups and CI working without credentials).
- **Brevo** (`EMAIL_BACKEND` → `notifications.brevo_backend.
  BrevoEmailBackend`) — OTP codes, password reset links, reminder emails,
  sent via Brevo's HTTP API. Chosen over SMTP because Render blocks
  outbound SMTP ports on its free tier and SMTP providers in general are
  unreliable from cloud/datacenter IPs. The backend is a normal Django
  `EMAIL_BACKEND`, so `notifications/email_service.py` and every call site
  still just call `send_mail` unchanged; swapping providers again later
  means writing a new `EMAIL_BACKEND` class, not touching call sites.

## Caching

None. No `CACHES` backend beyond Django's in-memory default, no Redis-as-
cache usage (Redis here is Celery's broker/result backend only, not a
general cache). Every read hits Postgres directly. If a future bottleneck
justifies caching, that's a deliberate addition, not something to
casually bolt onto an existing view.

## Deployment architecture

Split-host production deploy, not a single Docker Compose stack:
- **Frontend** — Vercel (static Vite build). Env vars: `VITE_API_ROOT`,
  `VITE_GOOGLE_CLIENT_ID` only.
- **Backend** — Render Web Service (free tier — cold-starts after idle,
  see Background jobs above). Env vars per `.env.render` (gitignored,
  never commit or paste its contents anywhere).
- **Database** — Supabase-hosted Postgres, connected via
  `DATABASE_URL_PROD` (Supabase's connection pooler URL), SSL required.
- **Scheduled jobs** — GitHub Actions cron (see Background jobs), not a
  Celery worker/beat process — this is the free-tier substitute, and it's
  why `INTERNAL_TASK_KEY` exists as a repo secret shared between GitHub
  Actions and Render's env.
- **CI** — `.github/workflows/ci.yml` runs the backend test suite against
  real `postgres:16-alpine` + `redis:7-alpine` service containers on every
  push/PR, and is `workflow_call`-able (reusable) rather than duplicated
  logic.

`docker-compose.yml` is a separate, self-contained deployment option
(Postgres + Redis + backend + Celery worker + Celery beat + frontend, all
containerized) — used for self-hosting or a from-scratch local full-stack
run, not what production actually runs on. Don't assume production
behavior (e.g. "there's a Celery worker") from reading
`docker-compose.yml` alone; check which environment you're reasoning
about first.

## Concurrency rules

- **GitHub Actions scheduled-tasks workflow**: `concurrency: { group:
  scheduled-tasks, cancel-in-progress: false }` — a slow "frequent" run
  and an overlapping "daily" run queue rather than cancel each other,
  because most individual scheduled tasks are already idempotent and
  overlap is cheap to avoid by just not cancelling.
- **JWT rotation**: `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`
  means a refresh token is single-use — two concurrent refresh calls with
  the same token will have one winner and one that hits an already-
  blacklisted token. This is intentional (replay protection), not a bug
  to work around.
- **Copilot recommendations**: approving one executes immediately via
  `ActionAgent`, but the Beat/cron `run_action_agent_sweep` also runs
  every 15 minutes and picks up anything approved-but-not-yet-executed —
  these two paths are expected to race harmlessly (the sweep is a
  catch-all for the immediate path failing/timing out), not something
  that needs a lock. `ActionAgent` execution should stay idempotent
  against being invoked twice for the same recommendation.
