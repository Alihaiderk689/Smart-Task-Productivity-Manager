# Memory Index

Per-feature memory for this project. Each file explains how one feature
actually works: key files, models, endpoints, invariants, and gotchas that
aren't obvious just from reading the code. See [CLAUDE.md](../../CLAUDE.md)
for the convention that keeps this index and its files up to date.

| Feature | File | Backend app(s) |
|---|---|---|
| Auth & user accounts | [auth-users.md](auth-users.md) | `users` |
| Tasks (CRUD + lifecycle) | [tasks.md](tasks.md) | `tasks` |
| Categories | [categories.md](categories.md) | `categories` |
| Dashboard | [dashboard.md](dashboard.md) | `dashboard` |
| Analytics | [analytics.md](analytics.md) | `analytics` |
| Reminders & notifications | [notifications-reminders.md](notifications-reminders.md) | `notifications` |
| Admin panel | [adminpanel.md](adminpanel.md) | `adminpanel` |
| AI Admin Copilot | [copilot-admin.md](copilot-admin.md) | `copilot` |
| User-tier Copilot chat | [usercopilot.md](usercopilot.md) | `usercopilot` |
| Evaluation framework | [evaluation.md](evaluation.md) | `evaluation` |
| Core infra & scheduled jobs | [core-infra.md](core-infra.md) | `core` |
| Frontend (React/Vite) | [frontend.md](frontend.md) | `frontend/` |

For system-wide *why* (deployment shape, DB design, external APIs), the
root [ARCHITECTURE.md](../../ARCHITECTURE.md) and [SECURITY.md](../../SECURITY.md)
are still the source of truth — these feature files are the next level
down, closer to the code.
