---
name: auth-users
description: JWT + Google OAuth + OTP email verification, profile/avatar. Access token held in JS memory only; refresh token in HttpOnly cookie.
app: users
updated: 2026-08-28
---

## What it does

Account creation/login and the `Profile`/avatar. Three ways to establish
identity, all converging on the same JWT issuance (see
[ARCHITECTURE.md](../../ARCHITECTURE.md#authentication-architecture) for
the full *why*):

1. **Email/password + OTP** — `signup` creates the user inactive-for-login
   until `verify_email_otp` succeeds.
2. **Google OAuth** — `google_login` verifies the ID token server-side,
   finds-or-creates the local `User` from the verified email.
3. **Password reset** — `request_password_reset` / `confirm_password_reset`,
   out-of-band token flow, ends in a normal `login`.

## Key files

- `backend/users/models.py` — `Profile` (avatar), `EmailOTP` (one row per
  user, replaced on each send; `code_hash`, `expires_at`, `attempts`,
  `send_count`).
- `backend/users/otp.py` — OTP generation/hashing/verification, resend
  lockout (`MAX_SENDS_PER_CYCLE`, `RESEND_LOCKOUT`).
- `backend/users/views.py` — all endpoints.
- `backend/users/token_cookies.py` — sets/reads the HttpOnly refresh cookie.
- `backend/users/throttling.py`, `validators.py`, `imaging.py` (avatar
  crop/resize), `serializers.py`.
- `backend/README_AUTH.md` — user-facing endpoint reference, kept
  separately because it documents request/response shapes, not internals.

## Endpoints (`backend/users/urls.py`, mounted under `/api/`)

`signup/`, `login/`, `google-login/`, `profile/`,
`profile/change-password/`, `token/refresh/` (reads refresh token from the
HttpOnly cookie, **not** simplejwt's stock `TokenRefreshView`), `logout/`,
`password-reset/`, `password-reset/confirm/`, `verify-email/`,
`verify-email/resend/`.

## Invariants / gotchas

- **Access token: JS-memory only, never localStorage.** Frontend mirror:
  `frontend/src/services/api.js`'s module-level `accessToken` variable.
  Disappears on tab close/hard reload by design — see
  [frontend.md](frontend.md) and `SECURITY.md`'s "Token storage" section.
- **Refresh token never reaches JS** — HttpOnly cookie only, attached
  automatically by the browser (`withCredentials: true`) to
  `/token/refresh/` and `/logout/`. This is why CORS (explicit origin
  allowlist + `CORS_ALLOW_CREDENTIALS=True`), not CSRF tokens, is the
  primary cross-origin defense for the Bearer-authenticated majority of
  the API.
- A new user is **inactive for login** until OTP verification succeeds —
  don't assume `signup` alone produces a usable session.
- `bholarecord699@gmail.com` is the staff/admin test account used for
  manual verification throughout the project (password known to the user,
  not recorded anywhere in the repo).

## Touches / related

[frontend.md](frontend.md) (AuthContext, ProtectedRoute/RoleRoute),
[adminpanel.md](adminpanel.md) (staff deactivate/activate/delete acts on
this app's `User` model).
