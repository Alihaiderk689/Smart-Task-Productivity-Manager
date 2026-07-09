Authentication API

Endpoints

- POST /api/signup/
  - Body: {"first_name":"Alice","email":"alice@example.com","password":"secret"}
  - Returns: user info + `access` and `refresh` JWT tokens

- POST /api/login/
  - Body: {"email":"alice@example.com","password":"secret"}
  - Returns: user info + `access` and `refresh` JWT tokens

- GET /api/profile/
  - Protected: send header `Authorization: Bearer <access>`
  - Returns: basic user info

- POST /api/token/refresh/
  - Body: {"refresh": "<refresh_token>"}
  - Returns: new `access` token

- POST /api/logout/
  - Body: {"refresh": "<refresh_token>"}
  - Blacklists the refresh token (logout)

Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
```

Environment

1. Copy `.env.example` to `.env` and edit values (or run `scripts/create_env.sh`):

```bash
cp .env.example .env
```

2. When `POSTGRES_DB` is set in `.env`, the project will use Postgres; otherwise it will use SQLite (`db.sqlite3`).

Frontend example files are available in the `frontend_examples/` folder. There is an `auth.js` helper showing `signup`, `login`, `refreshToken`, `logout`, and `profile` usage.

Frontend usage examples

Fetch (native):

```js
const token = '<ACCESS_TOKEN>'
fetch('http://127.0.0.1:8000/api/profile/', {
  headers: { 'Authorization': `Bearer ${token}` }
}).then(r => r.json()).then(console.log)
```

Axios:

```js
axios.get('http://127.0.0.1:8000/api/profile/', {
  headers: { Authorization: `Bearer ${token}` }
}).then(resp => console.log(resp.data))
```

Refresh token example (Axios):

```js
axios.post('http://127.0.0.1:8000/api/token/refresh/', { refresh: refreshToken })
  .then(r => {
    const newAccess = r.data.access;
    // store and use newAccess
  })
```

Logout (blacklist refresh):

```js
axios.post('http://127.0.0.1:8000/api/logout/', { refresh: refreshToken })
  .then(() => {
    // remove tokens from storage
  })
```

Notes

- Settings default to SQLite for local development. To use Postgres in production, set these env vars: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`.
- Passwords are hashed with bcrypt (configured in `config/settings.py`).
- Tokens are provided by `djangorestframework-simplejwt`.
 - Refresh token rotation is enabled by default (`ROTATE_REFRESH_TOKENS=True`) and the backend blacklists refresh tokens after rotation. The `/api/token/refresh/` endpoint may therefore return a new `refresh` token; frontend code should replace the saved refresh token when present.
