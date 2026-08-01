Authentication API

Endpoints

- POST /api/signup/
  - Body: {"first_name":"Alice","email":"alice@example.com","password":"secret"}
  - Creates the account (inactive) and emails a 6-digit verification code. Returns user info only -- no tokens yet.

- POST /api/verify-email/
  - Body: {"email":"alice@example.com","otp":"123456"}
  - Activates the account if the code is correct and not expired (10 min TTL, 5 wrong guesses locks it -- request a new code). Returns user info + `access` and `refresh` JWT tokens, logging them in.

- POST /api/verify-email/resend/
  - Body: {"email":"alice@example.com"}
  - Always returns a generic message (doesn't reveal whether the account exists). Sends a new code unless one was already sent in the last 60 seconds.

- POST /api/login/
  - Body: {"email":"alice@example.com","password":"secret"}
  - Returns: user info + `access` and `refresh` JWT tokens (403 if the account hasn't completed email verification yet)

- GET /api/profile/
  - Protected: send header `Authorization: Bearer <access>`
  - Returns: basic user info

- POST /api/token/refresh/
  - Body: {"refresh": "<refresh_token>"}
  - Returns: new `access` token

- POST /api/logout/
  - Body: {"refresh": "<refresh_token>"}
  - Blacklists the refresh token (logout)

- POST /api/google-login/
  - Body: {"credential": "<Google ID token>"}
  - Verifies the ID token from Google's "Sign in with Google" button, creates
    the account on first login (email/name from the token, no password), and
    returns user info + `access` and `refresh` JWT tokens -- same shape as
    /api/login/.

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

Google sign-in setup

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), create an **OAuth client ID** of type "Web application".
2. Add these to **Authorized JavaScript origins**: `http://localhost:5173` (dev) and your deployed frontend URL.
3. Copy the generated client ID into `GOOGLE_CLIENT_ID` in `backend/.env` and `VITE_GOOGLE_CLIENT_ID` in `frontend/.env` (same value in both).
4. Restart both dev servers. The "Or continue with Google" button on the login/register pages is hidden automatically when `VITE_GOOGLE_CLIENT_ID` is blank.

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
