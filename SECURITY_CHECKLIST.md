# SECURITY_CHECKLIST.md

Pre-deploy checklist. For the reasoning behind each item, see
[SECURITY.md](SECURITY.md). Run through this before any production
release, not just the first one — env drift (a var quietly reset to a
dev default) is the most common way these regress.

## Django core

- [ ] `DEBUG=False` (`config/settings.py` reads `DEBUG` case-insensitively
      from env now, but confirm the env var itself is set — the code
      default is `True`).
- [ ] `SECRET_KEY` is set via env, not committed, and is not the
      CI-only placeholder (`ci-test-secret-key-not-for-production` from
      `.github/workflows/ci.yml`) or any other example value.
- [ ] `ALLOWED_HOSTS` includes only the real production hostname(s) —
      not `localhost`/`127.0.0.1` left over from the default.
- [ ] `ENVIRONMENT=production` — this alone gates
      `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
      `CSRF_COOKIE_SECURE`, and `ssl_require=True` on the DB connection.
      Verify it's actually set, not just `DEBUG=False` (they're
      independent switches).

## Secrets

- [ ] No `.env`, `.env.render`, or equivalent file is committed to git
      (`git ls-files | grep -i '\.env'` should show only `.env.example`
      files).
- [ ] `SECRET_KEY`, `INTERNAL_TASK_KEY`, DB credentials, `GROQ_API_KEY` /
      `GEMINI_API_KEY` / `OPENROUTER_API_KEY`, `GOOGLE_CLIENT_ID`,
      Cloudinary credentials, and `RESEND_API_KEY` are all set via the
      hosting platform's env var UI (Render/Vercel/GitHub Actions
      secrets), not hardcoded anywhere.
- [ ] `INTERNAL_TASK_KEY` matches exactly between the Render backend env
      and the GitHub Actions repo secret — a mismatch fails scheduled
      tasks silently until someone checks the workflow run logs.
- [ ] No secret value has been pasted into a chat, issue, commit message,
      or log line during setup/debugging.

## CORS

- [ ] `CORS_ALLOWED_ORIGINS` lists only real frontend origin(s) — no
      `localhost:5173` left in the production list, no
      `CORS_ALLOW_ALL_ORIGINS = True` anywhere.
- [ ] `FRONTEND_URL` env var matches the actual deployed frontend URL
      exactly (used both for CORS and for links built into emails).

## CSRF trusted origins

- [ ] If anything relies on session-cookie auth behind HTTPS (notably
      Django's built-in `/admin/` site), `CSRF_TRUSTED_ORIGINS` includes
      that origin with its scheme (`https://...`) — Django 4.x requires
      the scheme explicitly. Not required for the JWT-based API itself,
      which doesn't use session cookies — see
      [SECURITY.md](SECURITY.md#csrf).

## Cookies

- [ ] `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are both `True` in
      production (confirm `ENVIRONMENT=production` is actually set — see
      above, these are gated on it, not on `DEBUG`).

## Security headers (see SECURITY.md §7 for full detail)

- [ ] `SECURE_HSTS_SECONDS = 31536000` is in effect in production
      (`config/settings.py`, gated on `ENVIRONMENT == "production"`) —
      `config/test_security_headers.py` confirms the header appears under
      a simulated production config, but that's still [DEPLOY: local] per
      SECURITY.md's tagging — confirm the *real* deployed response
      actually carries `Strict-Transport-Security` too (e.g. `curl -I`
      the production URL), not just that the setting/test exist.
- [ ] The frontend build's CSP `<meta>` tag (injected by
      `frontend/vite.config.js`'s `htmlSecurityHeaders` plugin) still
      allows `https://accounts.google.com` (Google Sign-In's script *and*
      its stylesheet) and the Cloudinary asset domain — if a new external
      script/style/image host is added anywhere in the frontend, it needs
      a matching addition there or it silently breaks (CSP fails closed,
      not with an obvious error to the user).
- [ ] If `VITE_API_ROOT` changes to a new cross-origin backend URL, no
      manual CSP update is needed — it's computed from that same env var
      at build time — but worth a quick sanity check that the built
      `dist/index.html`'s CSP `connect-src`/`img-src` actually contains
      the new origin after the next deploy.

## Token exposure — see SECURITY.md §1 (fixed)

- [ ] The access token still lives only in memory
      (`frontend/src/services/api.js`) and the refresh token only in the
      `HttpOnly` cookie (`backend/users/token_cookies.py`) — neither in
      `localStorage`/`sessionStorage`. If either regresses in a future
      change, update this checklist and SECURITY.md together, not
      separately.
- [ ] In production specifically, confirm the refresh cookie is actually
      arriving with `Secure; SameSite=None` (check a real login response's
      `Set-Cookie` header) — `REFRESH_COOKIE_SECURE`/
      `REFRESH_COOKIE_SAMESITE` are gated on `ENVIRONMENT=production`
      the same way the other cookie flags are, so this silently reverts
      to the dev values (`SameSite=Lax`, no `Secure`) if that env var is
      ever unset in production, breaking cross-site login entirely (not
      a silent security regression in that direction, but worth knowing
      as a failure mode).

## Database

- [ ] Production database connection uses `DATABASE_URL_PROD` with
      `ssl_require=True` (automatic when `ENVIRONMENT=production`) — not
      falling through to a `POSTGRES_*` discrete-var override meant for
      Docker Compose/CI.
- [ ] No Postgres RLS is assumed to exist — user data isolation is
      enforced entirely by `get_queryset()` filtering in the ORM layer
      (see [SECURITY.md](SECURITY.md#user-data-isolation)); confirm every
      new per-user view added since the last release actually filters by
      `request.user`.
- [ ] Database credentials are the production Supabase (or equivalent)
      credentials, not a dev/CI database.

## Authentication endpoints

- [ ] Every unauthenticated endpoint (`signup`, `login`, `google_login`,
      `verify_email_otp`, `resend_email_verification`,
      `request_password_reset`, `confirm_password_reset`) is rate-limited
      via `@throttle_classes([AuthRateThrottle])` — grep
      `users/views.py` to confirm none were added without it.
- [ ] `PASSWORD_RESET_TIMEOUT` is still short (currently 120s) — don't
      let this silently drift longer during unrelated edits.
- [ ] Google OAuth verification still calls
      `google_id_token.verify_oauth2_token` server-side (never trust a
      client-supplied profile payload).

## Admin endpoints

- [ ] Every view in `adminpanel/`, `copilot/`, and `evaluation/` carries
      `IsAdminUser` — grep for `permission_classes` in those three apps
      and confirm no view is missing it or was left on the DRF default.
- [ ] No sensitive copilot tool (`deactivate_user`, `send_reminder`,
      `delete_completed_tasks`, or any new one) has been added to the
      chat service's exposed tool schema
      (`copilot/services/chat_service.py`) — sensitive tools must only be
      reachable via `propose_action` → human approval → `ActionAgent`.
- [ ] No user-facing (non-admin) serializer in `users/` accepts
      `is_staff` as writable input.

## Rate limiting

- [ ] `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES` (`auth`, `internal_tasks`,
      `health`, `copilot_chat`, `evaluation_run`) are all still present
      and at sane values — an accidental removal silently un-throttles
      the corresponding views since the throttle classes reference these
      scopes by name.
- [ ] `copilot_chat` (20/min) and `evaluation_run` (5/hour) still decorate
      `chat_send` (`copilot/views.py`) and `trigger_evaluation`
      (`evaluation/views.py`) respectively — both trigger real, billed
      LLM calls per request, so losing the throttle here is a cost risk,
      not just an abuse risk.

## Logging

- [ ] No log statement anywhere prints a password, OTP code, JWT, or API
      key. Spot-check any new `logger.info`/`logger.exception` calls
      added near `users/views.py`, `copilot/llm/`, or anywhere handling
      credentials.
- [ ] `LOGGING` config (`config/settings.py`) still routes to console
      only in this deployment — confirm nothing was added that ships
      logs to a third party without review.

## Scheduled tasks (production-specific)

- [ ] `run_scheduled_tasks` (`core/views.py`) is still gated by
      `INTERNAL_TASK_KEY` via the `X-Internal-Task-Key` header, and still
      404s identically for both a bad key and an unknown route (so a
      scanner can't distinguish "wrong key" from "route doesn't exist").
- [ ] `.github/workflows/scheduled-tasks.yml`'s cron entries still match
      `config/celery.py`'s `beat_schedule` — a new Beat entry does
      nothing in production until this workflow (and
      `run_scheduled_tasks`' group dispatch) is updated to match.

## Dependencies

- [ ] CI's `pip-audit`/`npm audit` steps (`.github/workflows/ci.yml`) are
      green — if either newly fails, something *new* was introduced
      (both already tolerate every currently-known, individually-triaged
      finding via an explicit ignore list — see SECURITY.md §23) — don't
      widen the ignore list to make a new failure go away without the
      same triage.
- [ ] Django (4.2.30), pytest (7.4.4), Pillow (11.3.0), and
      `react-router-dom` (6.x) are still tracked as outstanding
      major-version security debt (SECURITY.md "Still open") —
      periodically reassess whether it's time to schedule the upgrade,
      rather than letting the CI ignore list / `--audit-level=high`
      threshold become a permanent way of not looking at them.
- [ ] GitHub Dependabot alerts and secret scanning + push protection are
      enabled for the repo (Settings → Code security) — zero-code-change,
      currently unconfirmed/likely off.

## Session revocation on security-sensitive events — see SECURITY.md §1 (fixed)

- [ ] Changing a password (`change_password`) or completing a password
      reset (`confirm_password_reset`) both now blacklist every
      outstanding refresh token for that account
      (`token_cookies.revoke_all_outstanding_tokens`) — confirm this
      hasn't been quietly removed from either view. Still true and worth
      remembering: an *access* token issued before the event remains
      valid for its own remaining (now 15-minute) lifetime regardless —
      this revokes refresh tokens, not already-issued access tokens.
