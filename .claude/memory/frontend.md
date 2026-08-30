---
name: frontend
description: React/Vite SPA — role-split routing (Layout vs AdminLayout via RoleRoute), in-memory access token + HttpOnly refresh cookie, react-query for server state.
app: frontend/
updated: 2026-08-30
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
- `src/components/Copilot*.jsx`, `Chat*.jsx` — the copilot chat UI, two
  separate surfaces sharing one `Textarea`-autosize hook
  (`src/hooks/use-autosize-textarea.jsx` — grows the input with typed
  content up to `maxHeight`, then scrolls internally, same pattern both
  places): `CopilotChat`/`ChatHeader`/`ChatMessages`/`ChatMessage`/
  `ChatInput`/`CopilotButton` are the floating widget on `Home.jsx`
  (user-tier, `usercopilot` backend); `CopilotQueryBox` is the embedded
  box on `Admin.jsx` and `AdminCopilot.jsx` (admin-tier, `copilot`
  backend) — self-contained, doesn't reuse `ChatInput`/`ChatMessages`.

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

## Server state: TanStack Query (added 2026-08-30)

`Home.jsx`, `Tasks.jsx`, `TaskDetail.jsx`, `Categories.jsx` were the last
holdouts still doing manual `useState`+`useEffect(loadData)` fetching with
**no error handling at all** (a failed request silently rendered as empty
data) — now on real `useQuery`/`useMutation` via
`src/hooks/use-tasks.jsx` (`useTasksQuery`, `useTaskQuery(id)`,
`useCategoriesQuery`, `useTaskActionMutation`, `useDeleteTaskMutation`) and
`src/components/query-state.jsx` (`LoadingSpinner`, `ErrorState` — shared,
reusable loading/error UI with a retry button wired to `refetch()`).
`TaskForm` (`components/taskform.jsx`) itself was **not** touched — its
`onSaved` callback is just rewired per-page to
`queryClient.invalidateQueries()` instead of a manual refetch.

Hooks still call through `base44.entities.*` (the `api/base44Client.js`
shim over `services/api.js`'s `tasksApi`/`categoriesApi`), not those
modules directly — same functions every page already called, now inside
`queryFn`/`mutationFn`. `TaskDetail.jsx`'s query is keyed `['tasks', id]`
(see [tasks.md](../../.claude/memory/tasks.md)'s pagination section for the
backend side) — switching between two tasks' detail pages is a genuinely
new query key, so no stale cross-task data can leak and loading correctly
re-arms per id, with no manual bookkeeping. It also distinguishes a real
404 (`error.response.status === 404`, "Task not found") from any other
fetch error (retryable `ErrorState`) — previously both collapsed into one
`!task` branch. `useTaskQuery`'s `retry` option matches the app-wide
default (`queryClientInstance`'s `retry: 1`) but skips retrying a 404 or a
401 specifically — a 404 can never succeed on retry, and a 401 has already
had one refresh+replay attempt inside `apiClient`'s response interceptor
(`services/api.js`) before the query ever sees the error, so retrying here
would just be a second, redundant refresh attempt. Any other tool/page
adding its own custom `retry` should follow the same shape rather than
inventing a different retry count, to avoid page-to-page inconsistency.

**checkJs gotcha**: `jsconfig.json`'s `include` only covers
`src/pages/**/*.jsx` (plus `src/components/**/*.js` and `src/Layout.jsx`),
but `tsc` still transitively type-checks anything those files import — so
`src/hooks/use-tasks.jsx` gets checked even though `src/hooks/` isn't
itself included. TanStack Query's generics can't be inferred from a plain
destructured JS parameter under checkJs (`TVariables` silently defaults to
`void`), and `onError`/`retry` callbacks get typed against the library's
default `TError = Error`, not axios's actual shape (`.response`). Fix
pattern used throughout `use-tasks.jsx` and the pages: `/** @type {any} */`
casts on the options object passed to `useMutation`/`useQuery` (and, for
mutations whose `.mutate()` call site also errors, on the hook's *return
value* too) rather than fighting the inference. `**/*.test.jsx` is
excluded from `jsconfig.json` entirely (vitest type-checks nothing itself)
— a `.test.jsx` colocated under `src/pages/` would otherwise get pulled
into the same strict include glob as the real page files.

## Role enforcement

`RoleRoute` (`src/components/RoleRoute.jsx`) gates on the profile's
`is_staff`, redirecting a mismatched role rather than just hiding nav
links — treat this as the actual security boundary on the frontend side
(the real boundary is still backend `IsAdminUser`/`IsAuthenticated`, this
is defense-in-depth / UX, not the enforcement point).

## Testing (added 2026-08-30)

`vitest` + `@testing-library/react` + `jsdom` — first frontend test infra
in this repo (`npm test`, wired into `frontend-checks` CI job right after
lint/typecheck). Config lives in `vite.config.js`'s `test` block (not a
separate `vitest.config.*`), setup file at `src/test/setup.js`
(`@testing-library/jest-dom` matchers). Shared render helper:
`src/test/render.jsx`'s `renderWithProviders()` (fresh retry-disabled
`QueryClient` + `MemoryRouter` per render). Existing test files: `ProtectedRoute`/
`RoleRoute` (mock `useAuth()`), `use-tasks` (API failure surfaces
`isError`), `Tasks` (loading/empty/list states), `TaskDetail` (404 vs.
retryable error, a mutation firing the right API call + toast). Deliberately
not exhaustive — lightweight coverage of the highest-value paths only.
`useTaskQuery`'s own retry-on-non-404 logic overrides the test
QueryClient's `retry: false` default (a query-level option always beats
the client default), so the one test exercising a 500 genuinely waits out
real backoff delays (~3s) — that's expected, not flaky.

## Dead-code cleanup (2026-08-30)

`vite.config.jsx` (never loaded — Vite's default config resolution doesn't
pick up `.jsx`, only `.js/.mjs/.ts/.cjs/.mts/.cts`; the real config is
`vite.config.js`), `src/api/taskflow.js` (the actual unused `@base44/sdk`
client — confusingly named almost the same as the real, live shim
`src/api/base44Client.js`), `src/lib/app-params.js`, and
`src/components/TaskFlowPro.jsx` (imported from a `./taskflow/` subdir that
doesn't even exist) were all base44-scaffold leftovers with zero live
imports — deleted, along with the now-unused `@base44/sdk`/
`@base44/vite-plugin` deps. **Removing them exposed a real pre-existing
bug**: `services/api.js` imports `axios` directly but it was never
declared in `package.json` — it only worked because `@base44/sdk`
transitively pulled it in. Now declared explicitly as a direct dependency.

## Touches / related

[auth-users.md](auth-users.md) (token model, endpoints this app calls),
every backend feature file (each has a corresponding page/component
here) — [tasks.md](tasks.md) ↔ `Tasks.jsx`/`TaskDetail.jsx`/
`taskform.jsx`, [categories.md](categories.md) ↔ `Categories.jsx`,
[copilot-admin.md](copilot-admin.md) ↔ `AdminCopilot.jsx` +
`Copilot*.jsx`/`Chat*.jsx`, [evaluation.md](evaluation.md) ↔
`AdminEvaluation.jsx`, [adminpanel.md](adminpanel.md) ↔ `Admin.jsx` +
`AdminTasks.jsx`.
