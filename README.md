# Smart Task & Productivity Manager

A full-stack task manager with time-boxed tasks, email reminders, and a productivity dashboard. Django REST Framework API on the backend, React on the frontend, with Celery handling scheduled and recurring reminder emails.

## Features

- **Task lifecycle** — create, start, pause, resume, stop, complete, or reschedule a task; status transitions are enforced server-side (e.g. you can't complete a task you never started).
- **Email reminders**, powered by Celery:
  - 30 minutes and 5 minutes before a task's start time
  - A nudge if you haven't started a task ~40% of the way through its scheduled window
  - An "overdue" email when a task's end time passes without completion, with a one-click reschedule link — the task is automatically marked **Missed** at the same time (unless it was already completed or deliberately stopped)
  - A recurring **daily check-in** for multi-day tasks (span > 1 day), via a Celery Beat job — separate from the per-task reminders above, since it's one fixed schedule that sweeps every user's active long-running tasks rather than a one-off timer per task
- **Categories** — per-user tags for organizing tasks, seeded with sensible defaults on signup.
- **Dashboard & analytics** — today's tasks, upcoming tasks, high-priority tasks, missed tasks, a productivity score, and weekly/monthly completion charts.
- **Accounts**
  - JWT authentication (access + refresh, rotation, blacklisting on logout)
  - Mandatory email verification before first login (accounts are inactive until the emailed link is clicked)
  - Forgot-password flow with a short-lived (2 minute) reset link that logs you straight in once used
  - Rate limiting on signup/login/password-reset to slow down brute-force attempts
- **Profile** — display name, avatar upload with an in-browser crop/zoom step before it's saved, change password.
- **Dark / light theme**, respecting your OS preference by default, togglable and persisted.

## Tech stack

| | |
|---|---|
| **Backend** | Django 4.2, Django REST Framework, SimpleJWT, Celery, Redis, PostgreSQL |
| **Media storage** | Local disk in dev, Cloudinary in production (swappable via env vars, no code changes) |
| **Frontend** | React 18, Vite, React Router, TailwindCSS, Radix UI (shadcn-style components), TanStack Query |
| **Testing** | pytest / pytest-django (backend), ESLint (frontend) |

## Architecture

Five processes make up a full local run:

```
Django (manage.py runserver)  →  serves the REST API
Vite (npm run dev)             →  serves the React frontend
PostgreSQL                     →  primary datastore
Redis                          →  Celery's message broker
Celery worker + Beat           →  sends reminder emails (scheduled + recurring)
```

Redis and Celery are independent of Django — starting the backend does **not** start them. See [Running the app](#running-the-app).

Two scheduling mechanisms are used deliberately for two different jobs: the per-task reminders (30-min-before, overdue, etc.) are scheduled individually via `apply_async(eta=...)` at the exact instant they're needed, while the daily multi-day check-in runs on a fixed recurring Celery Beat schedule that sweeps across every user's tasks. The former needs precision tied to one task's own timestamps; the latter needs a cadence that's the same for everyone, regardless of any single task's schedule.

## Project structure

```
backend/
  config/          settings, root URLs, Celery app + Beat schedule
  users/           auth, JWT, profile, avatar, email verification, password reset
  tasks/           the Task model and its lifecycle endpoints
  categories/      per-user task tags
  dashboard/       aggregate/summary read endpoints
  analytics/       productivity score, weekly/monthly stats
  notifications/   Celery tasks + email templates/sending (no models of its own)
frontend/
  src/pages/       route-level views (Login, Tasks, TaskDetail, Profile, ...)
  src/components/  shared UI (task form, layout/sidebar, date picker, avatar crop, ...)
  src/context/     Auth and Theme providers
  src/services/    Axios client + API calls
```

## Getting started

### Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL
- Redis

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill in the values described below

python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Environment variables (`backend/.env`)

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` or `production` — picks which database URL is used |
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL_DEV` / `DATABASE_URL_PROD` | Postgres connection string for each environment |
| `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL` | Brevo API key and sender address for reminder/auth emails (sent via the Brevo HTTP API, not SMTP) |
| `FRONTEND_URL` | Used to build links in emails (reset password, verify email, reschedule) |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Optional — avatar uploads fall back to local disk storage if left blank |

See `backend/.env.example` for the full list with placeholder values.

## Running the app

All four of these need to be running at once for the app to be fully functional (task CRUD works with just Django + the frontend; email reminders need Redis + Celery too):

```bash
# Terminal 1 — backend API
cd backend && source .venv/bin/activate && python manage.py runserver

# Terminal 2 — frontend
cd frontend && npm run dev

# Terminal 3 — Redis (skip if already running as a system service)
redis-server

# Terminal 4 — Celery worker + Beat scheduler
cd backend && source .venv/bin/activate && celery -A config worker -B --loglevel=info
```

Open the frontend at the URL Vite prints (typically `http://localhost:5173`).

## Docker

The whole stack (frontend, backend, Postgres, Redis, Celery worker + Beat)
also runs via Docker Compose — no local Python/Node install required.

```bash
cp .env.example .env   # fill in SECRET_KEY, POSTGRES_PASSWORD, etc.
docker compose up --build
```

Frontend: `http://localhost:8080` · Backend API: `http://localhost:8001/api`.
The frontend's nginx reverse-proxies `/api/`, `/admin/`, `/static/`, and
`/media/` to the backend container, so the published frontend image works
unmodified on any host.

Pre-built images are published to Docker Hub as
[`alihaider310/taskflow-backend`](https://hub.docker.com/r/alihaider310/taskflow-backend)
and [`alihaider310/taskflow-frontend`](https://hub.docker.com/r/alihaider310/taskflow-frontend).
Anyone with `docker-compose.yml` and a filled-in `.env` can skip the build:

```bash
docker compose pull
docker compose up
```

## Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

## API reference

A Postman collection covering the full API surface lives in `backend/postman/`. Broadly:

- `POST /api/signup/`, `/api/login/`, `/api/verify-email/`, `/api/verify-email/resend/`, `/api/token/refresh/`, `/api/logout/`
- `POST /api/password-reset/`, `/api/password-reset/confirm/`
- `GET/PATCH /api/profile/`, `POST /api/profile/change-password/`
- `GET/POST /api/tasks/`, `GET/PUT/PATCH/DELETE /api/tasks/<id>/`, plus `/start/`, `/pause/`, `/resume/`, `/stop/`, `/complete/`, `/reschedule/`
- `GET/POST /api/categories/`, `GET/PUT/PATCH/DELETE /api/categories/<id>/`
- `GET /api/dashboard/{summary,today,upcoming,high-priority,missed}/`
- `GET /api/analytics/{productivity,weekly,monthly}/`
