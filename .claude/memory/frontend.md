---
name: frontend
description: React/Vite SPA — role-split routing (Layout vs AdminLayout via RoleRoute), in-memory access token + HttpOnly refresh cookie, react-query for server state.
app: frontend/
updated: 2026-08-28
---

## What it does

The React/Vite SPA. Mirrors the backend's two-tier authorization split
structurally, not just with a permission check.

## Key files

- `src/App.jsx` — all routing. `PublicOnlyRoute` (login/register, blocked
  once authenticated) → `ProtectedRoute` (requires auth) →
  `RoleRoute allow="staff"|"user"` → layout (`AdminLayout` or `Layout`) →
  pages. A staff account only ever reaches `/admin/*`; a regular account
  never does — enforced here, not just hidden in the UI.
- `src/context/AuthContext.jsx` — session bootstrap, `user`/`accessToken`
  state, `signIn`/`signUp`/`checkUserAuth`/`syncProfile`.
- `src/services/api.js` — the axios clients and the token model (see
  below). `getErrorMessage`/`getFieldErrors` normalize DRF error
  responses (a non-JSON error body — HTML 500 page, proxy plaintext error
  — is a string here, not an object; naive `Object.values()` on it would
  wrongly iterate characters).
- `src/lib/query-client.jsx` — `@tanstack/react-query` setup for server
  state (tasks, categories, dashboard/analytics data).
- `src/pages/*.jsx` — regular-user pages (`Home`, `Tasks`, `TaskDetail`,
  `Categories`, `Calendar`, `Profile`) and staff pages (`Admin`,
  `AdminTasks`, `AdminCopilot`, `AdminEvaluation`, `AdminProfile`).
- `src/components/Copilot*.jsx`, `Chat*.jsx` — the copilot chat UI (used
  by both the admin copilot page and, presumably, a user-tier surface —
  confirm which before assuming one is unused).

## Token model — read before touching auth or any 401 handling

**Access token lives in a module-level JS variable in `services/api.js`
only — never localStorage/sessionStorage.** It disappears on tab close
and hard reload by design: an XSS payload could still read it out of
memory while the tab is open (nothing in a browser fully prevents that),
but it can't be exfiltrated as a durable, replayable credential the way a
localStorage value can. Session resume on load means asking the backend
to trade the HttpOnly refresh cookie (if any) for a fresh access token via
`bootstrapSession()`, then fetching the profile — there is nothing left
to read synchronously from client storage. `withCredentials: true` on
every axios client is required so the browser attaches the refresh
cookie. See [auth-users.md](auth-users.md) and `SECURITY.md`'s "Token
storage" section for the backend half.

## Role enforcement

`RoleRoute` (`src/components/RoleRoute.jsx`) gates on the profile's
`is_staff`, redirecting a mismatched role rather than just hiding nav
links — treat this as the actual security boundary on the frontend side
(the real boundary is still backend `IsAdminUser`/`IsAuthenticated`, this
is defense-in-depth / UX, not the enforcement point).

## Touches / related

[auth-users.md](auth-users.md) (token model, endpoints this app calls),
every backend feature file (each has a corresponding page/component
here) — [tasks.md](tasks.md) ↔ `Tasks.jsx`/`TaskDetail.jsx`/
`taskform.jsx`, [categories.md](categories.md) ↔ `Categories.jsx`,
[copilot-admin.md](copilot-admin.md) ↔ `AdminCopilot.jsx` +
`Copilot*.jsx`/`Chat*.jsx`, [evaluation.md](evaluation.md) ↔
`AdminEvaluation.jsx`, [adminpanel.md](adminpanel.md) ↔ `Admin.jsx` +
`AdminTasks.jsx`.
