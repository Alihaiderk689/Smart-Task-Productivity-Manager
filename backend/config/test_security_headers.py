"""Locks in the security-header claims made in SECURITY.md §7 -- without
this, a settings.py change could silently drop one of them and nothing
would notice until someone happened to inspect a raw response.

Django's SecurityMiddleware reads SECURE_HSTS_SECONDS etc. once, in
__init__, not per-request (see django/middleware/security.py) -- but
Django's test infrastructure rebuilds the middleware chain on
override_settings, so this still correctly reflects an overridden value.
Confirmed empirically before relying on it here, not assumed.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_hsts_header_present_when_configured():
    """Simulates the production SIMPLE_JWT/SecurityMiddleware config
    (config/settings.py's `if ENVIRONMENT == "production":` block) without
    actually running under ENVIRONMENT=production -- request.is_secure()
    also has to be true for SecurityMiddleware to emit the header at all,
    which `secure=True` on the test client provides."""
    client = APIClient()
    with override_settings(SECURE_HSTS_SECONDS=31536000, SECURE_HSTS_INCLUDE_SUBDOMAINS=True, SECURE_HSTS_PRELOAD=False):
        response = client.get("/api/core/health/", secure=True)

    header = response.get("Strict-Transport-Security")
    assert header is not None
    assert "max-age=31536000" in header
    assert "includeSubDomains" in header
    assert "preload" not in header


@pytest.mark.django_db
def test_hsts_header_absent_when_not_configured():
    """The inverse -- confirms the test above isn't a false positive from
    some other setting always emitting this header."""
    client = APIClient()
    with override_settings(SECURE_HSTS_SECONDS=0):
        response = client.get("/api/core/health/", secure=True)

    assert response.get("Strict-Transport-Security") is None


@pytest.mark.django_db
def test_default_django_security_headers_present():
    """Confirms the headers SECURITY.md §7 attributes to "Django's own
    default, unmodified" actually appear on a real response, rather than
    just trusting that reading global_settings.py implies they're active."""
    response = APIClient().get("/api/core/health/")

    assert response.get("X-Content-Type-Options") == "nosniff"
    assert response.get("Referrer-Policy") == "same-origin"
    assert response.get("X-Frame-Options") == "DENY"
    assert response.get("Cross-Origin-Opener-Policy") == "same-origin"
