"""Refresh-token-as-HttpOnly-cookie helpers.

Access tokens are returned in the JSON body and kept in memory by the
frontend (never persisted to localStorage). Refresh tokens are never sent
to JS at all -- they travel only in an HttpOnly cookie, so an XSS
vulnerability elsewhere in the SPA cannot read or exfiltrate them. See
SECURITY.md's "Token storage" section for the full threat model this
closes and what it deliberately doesn't (a stolen, still-live access
token remains valid for its own short lifetime either way).
"""

from django.conf import settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

REFRESH_COOKIE_NAME = "refresh_token"
# Scoped to /api/ rather than just the two endpoints that actually read it
# (/api/token/refresh/, /api/logout/) -- Django's HttpResponse.set_cookie()
# stores cookies in a dict keyed by name only, so calling it twice for the
# same name with two different `path` values doesn't produce two Set-Cookie
# headers, it just makes the second call overwrite the first. A single
# shared path is the correct fix, and /api/ (not "/") at least keeps this
# off any non-API routes. The cookie stays HttpOnly regardless, so being
# attached to more API requests than strictly necessary doesn't expose it
# to JS on any of those pages -- it just means views that don't read it
# ignore it.
REFRESH_COOKIE_PATH = "/api/"


def _cookie_kwargs():
    return {
        "httponly": True,
        "secure": settings.REFRESH_COOKIE_SECURE,
        "samesite": settings.REFRESH_COOKIE_SAMESITE,
        "path": REFRESH_COOKIE_PATH,
    }


def set_refresh_cookie(response, refresh_token_str):
    """Attaches `refresh_token_str` to `response` as an HttpOnly cookie."""
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token_str,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        **_cookie_kwargs(),
    )


def issue_tokens(response, user):
    """Mints a fresh token pair for `user`, sets the refresh token as an
    HttpOnly cookie on `response`, and returns the access token string for
    the caller to put in the JSON body."""
    refresh = RefreshToken.for_user(user)
    set_refresh_cookie(response, str(refresh))
    return str(refresh.access_token)


def clear_refresh_cookie(response):
    # delete_cookie must be called with the same `path` (and samesite, as
    # of Django 4.1+) the cookie was originally set with, or the browser
    # treats it as a different cookie and won't actually remove it.
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, samesite=settings.REFRESH_COOKIE_SAMESITE)


def revoke_all_outstanding_tokens(user):
    """Blacklists every refresh token ever issued to `user` that isn't
    already blacklisted -- used after a password change/reset so a stolen
    refresh token can no longer mint new access tokens. Does NOT
    invalidate any access token still within its own (short) lifetime --
    SimpleJWT's blacklist app only ever consults the blacklist during
    refresh-token rotation, not on every authenticated request. That
    residual window is exactly why ACCESS_TOKEN_LIFETIME is kept short
    (see config/settings.py)."""
    outstanding = OutstandingToken.objects.filter(user=user)
    BlacklistedToken.objects.bulk_create(
        (BlacklistedToken(token=token) for token in outstanding),
        ignore_conflicts=True,
    )
