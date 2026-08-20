from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .token_cookies import REFRESH_COOKIE_NAME


def assert_issues_refresh_cookie(response):
    """The refresh token must never appear in the JSON body (that's the
    whole point of the cookie-based redesign -- see SECURITY.md's Token
    storage section) -- only in an HttpOnly cookie."""
    assert "refresh" not in response.data
    assert REFRESH_COOKIE_NAME in response.cookies
    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie.value
    assert cookie["httponly"]


def signup_payload(**overrides):
    """A valid /api/signup/ payload with sensible defaults -- pass overrides
    for the field(s) a given test actually cares about."""
    payload = {
        "first_name": "Test User",
        "email": "signup-default@example.com",
        "password": "SecurePassword123!",
        "password_confirm": "SecurePassword123!",
    }
    payload.update(overrides)
    return payload

@pytest.mark.django_db
def test_signup_success(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="Alice", email="alice@example.com"),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    # No tokens yet -- account is inactive until the emailed code is entered.
    assert "access" not in response.data
    assert "refresh" not in response.data
    assert response.data["user"]["email"] == "alice@example.com"

    user = User.objects.get(email="alice@example.com")
    assert user.is_active is False
    assert len(mail.outbox) == 1
    assert "verification code" in mail.outbox[0].subject.lower()

@pytest.mark.django_db
def test_signup_seeds_default_categories(api_client):
    from categories.models import Category
    from categories.services import DEFAULT_CATEGORY_NAMES

    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="Bob", email="bob@example.com"),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED

    user = User.objects.get(email="bob@example.com")
    names = set(Category.objects.filter(user=user).values_list("name", flat=True))
    assert names == set(DEFAULT_CATEGORY_NAMES)

@pytest.mark.django_db
def test_signup_missing_fields(api_client):
    response = api_client.post(
        "/api/signup/",
        {
            "first_name": "Alice"
        },
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.data
    assert "password" in response.data
    assert "password_confirm" in response.data

@pytest.mark.django_db
def test_signup_duplicate_email(api_client, test_user):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="Another", email=test_user.email),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["email"][0] == "This email is already registered."

@pytest.mark.django_db
def test_signup_duplicate_email_is_case_insensitive(api_client, test_user):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="Another", email=test_user.email.upper()),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["email"][0] == "This email is already registered."

@pytest.mark.django_db
def test_signup_lowercases_and_trims_email(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(email="  Mixed.Case@Example.COM  "),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["user"]["email"] == "mixed.case@example.com"
    assert User.objects.filter(email="mixed.case@example.com").exists()

@pytest.mark.django_db
def test_signup_password_too_short(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(password="sh", password_confirm="sh"),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data

@pytest.mark.django_db
def test_signup_password_missing_complexity_requirements(api_client):
    # 8+ chars but no uppercase/digit/special -- must still be rejected.
    response = api_client.post(
        "/api/signup/",
        signup_payload(password="lowercaseonly", password_confirm="lowercaseonly"),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data

@pytest.mark.django_db
def test_signup_password_with_spaces_rejected(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(password="Has Space123!", password_confirm="Has Space123!"),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data

@pytest.mark.django_db
def test_signup_password_matching_email_rejected(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(email="Sameas@example.com", password="Sameas@example.com", password_confirm="Sameas@example.com"),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data

@pytest.mark.django_db
def test_signup_password_confirm_mismatch(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(password="SecurePassword123!", password_confirm="Different123!"),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["password_confirm"][0] == "Passwords do not match."

@pytest.mark.django_db
def test_signup_full_name_required(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name=""),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "first_name" in response.data

@pytest.mark.django_db
def test_signup_full_name_rejects_digits_and_symbols(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="Alice123"),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "first_name" in response.data

@pytest.mark.django_db
def test_signup_full_name_too_short(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="A"),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "first_name" in response.data

@pytest.mark.django_db
def test_signup_full_name_allows_hyphen_and_apostrophe(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="Mary-Jane O'Brien", email="maryjane@example.com"),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["user"]["first_name"] == "Mary-Jane O'Brien"

@pytest.mark.django_db
def test_signup_full_name_trims_whitespace(api_client):
    response = api_client.post(
        "/api/signup/",
        signup_payload(first_name="  Alice  ", email="trimname@example.com"),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["user"]["first_name"] == "Alice"

@pytest.mark.django_db
def test_login_success(api_client, test_user):
    response = api_client.post(
        "/api/login/",
        {
            "email": test_user.email,
            "password": "TestPass123!"
        },
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert_issues_refresh_cookie(response)
    assert response.data["user"]["email"] == test_user.email

@pytest.mark.django_db
def test_login_invalid_credentials(api_client, test_user):
    response = api_client.post(
        "/api/login/",
        {
            "email": test_user.email,
            "password": "WrongPassword!"
        },
        format="json"
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["detail"] == "Invalid credentials."

@pytest.mark.django_db
def test_google_login_creates_new_active_user(api_client, settings, monkeypatch):
    from categories.models import Category
    from categories.services import DEFAULT_CATEGORY_NAMES

    settings.GOOGLE_CLIENT_ID = "test-client-id"
    monkeypatch.setattr(
        "users.views.google_id_token.verify_oauth2_token",
        lambda credential, request, client_id: {
            "email": "newgoogleuser@example.com",
            "email_verified": True,
            "given_name": "Gigi",
        },
    )

    response = api_client.post("/api/google-login/", {"credential": "fake-token"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert_issues_refresh_cookie(response)
    assert response.data["user"]["email"] == "newgoogleuser@example.com"
    assert response.data["user"]["first_name"] == "Gigi"

    user = User.objects.get(email="newgoogleuser@example.com")
    assert user.is_active is True
    assert user.has_usable_password() is False
    names = set(Category.objects.filter(user=user).values_list("name", flat=True))
    assert names == set(DEFAULT_CATEGORY_NAMES)

@pytest.mark.django_db
def test_google_login_logs_in_existing_user_without_creating_duplicate(api_client, settings, monkeypatch, test_user):
    settings.GOOGLE_CLIENT_ID = "test-client-id"
    monkeypatch.setattr(
        "users.views.google_id_token.verify_oauth2_token",
        lambda credential, request, client_id: {
            "email": test_user.email,
            "email_verified": True,
            "given_name": "Test",
        },
    )

    response = api_client.post("/api/google-login/", {"credential": "fake-token"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["user"]["id"] == test_user.id
    assert User.objects.filter(email=test_user.email).count() == 1

@pytest.mark.django_db
def test_google_login_invalidates_attacker_set_password_on_reactivation(api_client, settings, monkeypatch):
    """An attacker who pre-registers someone else's email via the normal
    signup flow (creating an inactive account with a password only the
    attacker knows) must not be able to use that password once the real
    owner proves ownership via Google -- Google reactivating the account
    must invalidate whatever password was already set on it."""
    attacker_password = "AttackerChosenPassword1!"
    victim = User.objects.create_user(
        username="victim@example.com",
        email="victim@example.com",
        password=attacker_password,
        is_active=False,
    )

    settings.GOOGLE_CLIENT_ID = "test-client-id"
    monkeypatch.setattr(
        "users.views.google_id_token.verify_oauth2_token",
        lambda credential, request, client_id: {
            "email": "victim@example.com",
            "email_verified": True,
            "given_name": "Victim",
        },
    )

    response = api_client.post("/api/google-login/", {"credential": "fake-token"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    victim.refresh_from_db()
    assert victim.is_active is True
    assert victim.has_usable_password() is False
    assert not victim.check_password(attacker_password)

@pytest.mark.django_db
def test_google_login_rejects_unverified_email(api_client, settings, monkeypatch):
    settings.GOOGLE_CLIENT_ID = "test-client-id"
    monkeypatch.setattr(
        "users.views.google_id_token.verify_oauth2_token",
        lambda credential, request, client_id: {
            "email": "unverified@example.com",
            "email_verified": False,
        },
    )

    response = api_client.post("/api/google-login/", {"credential": "fake-token"}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert not User.objects.filter(email="unverified@example.com").exists()

@pytest.mark.django_db
def test_google_login_rejects_invalid_credential(api_client, settings, monkeypatch):
    settings.GOOGLE_CLIENT_ID = "test-client-id"

    def _raise(*args, **kwargs):
        raise ValueError("bad token")

    monkeypatch.setattr("users.views.google_id_token.verify_oauth2_token", _raise)

    response = api_client.post("/api/google-login/", {"credential": "fake-token"}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_google_login_requires_credential(api_client, settings):
    settings.GOOGLE_CLIENT_ID = "test-client-id"

    response = api_client.post("/api/google-login/", {}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_google_login_returns_503_when_not_configured(api_client, settings):
    settings.GOOGLE_CLIENT_ID = None

    response = api_client.post("/api/google-login/", {"credential": "fake-token"}, format="json")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

@pytest.mark.django_db
def test_profile_authenticated(auth_client, test_user):
    response = auth_client.get("/api/profile/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == test_user.email

@pytest.mark.django_db
def test_profile_unauthenticated(api_client):
    response = api_client.get("/api/profile/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_logout_success(api_client, test_user):
    """logout no longer reads a token from the request body -- it reads
    the HttpOnly refresh cookie the test client picked up automatically
    from the /api/login/ response (Django's test client persists cookies
    across requests, same as a real browser)."""
    login_response = api_client.post(
        "/api/login/", {"email": test_user.email, "password": "TestPass123!"}, format="json"
    )
    refresh_value = login_response.cookies[REFRESH_COOKIE_NAME].value
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

    response = api_client.post("/api/logout/", {}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["detail"] == "Logout successful."
    assert response.cookies[REFRESH_COOKIE_NAME].value == ""

    with pytest.raises(TokenError):
        RefreshToken(refresh_value)

@pytest.mark.django_db
def test_logout_without_cookie_still_succeeds(api_client, auth_client):
    """No refresh cookie present (already logged out elsewhere, cleared by
    the browser, etc.) -- logout stays idempotent rather than erroring."""
    response = auth_client.post("/api/logout/", {}, format="json")
    assert response.status_code == status.HTTP_200_OK

@pytest.mark.django_db
def test_logout_rejects_form_encoded_body(auth_client):
    """JSON-only parsing on purpose -- see the comment on logout() in
    views.py. A classic cross-site <form> POST can only send
    application/x-www-form-urlencoded or multipart/form-data, both
    rejected here with a 415, which is what actually blocks that CSRF
    vector (the browser-enforced Content-Type restriction on <form>, not
    anything this test can directly exercise cross-origin)."""
    response = auth_client.post("/api/logout/", {"anything": "value"})
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

@pytest.mark.django_db
def test_token_refresh_issues_new_access_token_and_rotates_cookie(api_client, test_user):
    login_response = api_client.post(
        "/api/login/", {"email": test_user.email, "password": "TestPass123!"}, format="json"
    )
    old_access = login_response.data["access"]
    old_refresh = login_response.cookies[REFRESH_COOKIE_NAME].value

    response = api_client.post("/api/token/refresh/", {}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert "refresh" not in response.data
    new_access = response.data["access"]
    assert new_access and new_access != old_access

    new_refresh = response.cookies[REFRESH_COOKIE_NAME].value
    assert new_refresh and new_refresh != old_refresh
    # ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION are on -- the old
    # refresh token must be dead now, not just superseded.
    with pytest.raises(TokenError):
        RefreshToken(old_refresh)

@pytest.mark.django_db
def test_token_refresh_rejects_form_encoded_body(api_client, test_user):
    login_response = api_client.post(
        "/api/login/", {"email": test_user.email, "password": "TestPass123!"}, format="json"
    )
    api_client.cookies[REFRESH_COOKIE_NAME] = login_response.cookies[REFRESH_COOKIE_NAME].value

    response = api_client.post("/api/token/refresh/", {"anything": "value"})
    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

@pytest.mark.django_db
def test_token_refresh_rejects_missing_cookie(api_client):
    """400, not 401 -- this endpoint must stay reachable with zero
    credentials (see PUBLIC_ENDPOINTS in config/test_authentication_filters.py),
    matching the original stock TokenRefreshView's behavior for a missing
    `refresh` field (a validation error, not an auth failure)."""
    response = api_client.post("/api/token/refresh/", {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_token_refresh_rejects_reused_rotated_token(api_client, test_user):
    """Using the same refresh cookie twice in a row must fail the second
    time -- proves rotation+blacklist is actually wired through the
    cookie-based view, not just present in SIMPLE_JWT settings that
    nothing consults."""
    login_response = api_client.post(
        "/api/login/", {"email": test_user.email, "password": "TestPass123!"}, format="json"
    )
    api_client.cookies[REFRESH_COOKIE_NAME] = login_response.cookies[REFRESH_COOKIE_NAME].value

    first = api_client.post("/api/token/refresh/", {}, format="json")
    assert first.status_code == status.HTTP_200_OK

    # Force the client back to the now-rotated-out original cookie instead
    # of the new one it just received, to simulate a copy of the old
    # refresh token being replayed (e.g. by an attacker who captured it
    # before rotation).
    api_client.cookies[REFRESH_COOKIE_NAME] = login_response.cookies[REFRESH_COOKIE_NAME].value
    second = api_client.post("/api/token/refresh/", {}, format="json")
    assert second.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_password_reset_request_sends_email_for_existing_user(api_client, test_user):
    response = api_client.post(
        "/api/password-reset/",
        {"email": test_user.email},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 1
    assert test_user.email in mail.outbox[0].to
    assert "/reset-password?uid=" in mail.outbox[0].alternatives[0][0]

@pytest.mark.django_db
def test_password_reset_request_unknown_email_returns_generic_response(api_client):
    response = api_client.post(
        "/api/password-reset/",
        {"email": "nobody@example.com"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 0

@pytest.mark.django_db
def test_password_reset_confirm_success(api_client, test_user):
    uid = urlsafe_base64_encode(force_bytes(test_user.pk))
    token = default_token_generator.make_token(test_user)

    response = api_client.post(
        "/api/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "BrandNewPass123!"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert_issues_refresh_cookie(response)

    test_user.refresh_from_db()
    assert test_user.check_password("BrandNewPass123!")

@pytest.mark.django_db
def test_password_reset_confirm_revokes_outstanding_refresh_tokens(api_client, test_user):
    """A reset is plausibly happening *because* the account was
    compromised -- any refresh token issued before the reset (e.g. one an
    attacker holds) must stop working once it completes."""
    old_refresh = RefreshToken.for_user(test_user)

    uid = urlsafe_base64_encode(force_bytes(test_user.pk))
    token = default_token_generator.make_token(test_user)
    response = api_client.post(
        "/api/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "BrandNewPass123!"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    with pytest.raises(TokenError):
        RefreshToken(str(old_refresh))

@pytest.mark.django_db
def test_password_reset_confirm_rejects_invalid_token(api_client, test_user):
    uid = urlsafe_base64_encode(force_bytes(test_user.pk))

    response = api_client.post(
        "/api/password-reset/confirm/",
        {"uid": uid, "token": "not-a-real-token", "new_password": "BrandNewPass123!"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_password_reset_confirm_rejects_reused_token(api_client, test_user):
    uid = urlsafe_base64_encode(force_bytes(test_user.pk))
    token = default_token_generator.make_token(test_user)

    first = api_client.post(
        "/api/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "BrandNewPass123!"},
        format="json"
    )
    assert first.status_code == status.HTTP_200_OK

    second = api_client.post(
        "/api/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "AnotherPass456!"},
        format="json"
    )
    assert second.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_profile_update_first_name(auth_client, test_user):
    response = auth_client.patch("/api/profile/", {"first_name": "Updated"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["first_name"] == "Updated"
    test_user.refresh_from_db()
    assert test_user.first_name == "Updated"

@pytest.mark.django_db
def test_profile_update_avatar(auth_client, test_user):
    from io import BytesIO
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = BytesIO()
    Image.new("RGB", (10, 10), color=(1, 2, 3)).save(buf, format="PNG")
    avatar = SimpleUploadedFile("avatar.png", buf.getvalue(), content_type="image/png")

    response = auth_client.patch("/api/profile/", {"avatar": avatar}, format="multipart")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["avatar"] is not None

    from users.models import Profile
    profile = Profile.objects.get(user=test_user)
    assert profile.avatar
    profile.avatar.delete(save=True)

@pytest.mark.django_db
def test_profile_update_avatar_is_resized(auth_client, test_user):
    from io import BytesIO
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = BytesIO()
    Image.new("RGB", (2000, 1500), color=(50, 150, 200)).save(buf, format="JPEG")
    avatar = SimpleUploadedFile("big.jpg", buf.getvalue(), content_type="image/jpeg")

    response = auth_client.patch("/api/profile/", {"avatar": avatar}, format="multipart")
    assert response.status_code == status.HTTP_200_OK

    from users.models import Profile
    profile = Profile.objects.get(user=test_user)
    stored = Image.open(profile.avatar)
    assert stored.width <= 512
    assert stored.height <= 512
    profile.avatar.delete(save=True)

@pytest.mark.django_db
def test_profile_update_rejects_non_image_avatar(auth_client, test_user):
    """ProfileUpdateSerializer.avatar is a DRF ImageField -- validation
    (Pillow-backed, same as resize_avatar_file's own Image.open()) runs
    during serializer.is_valid(), so a non-image file never reaches
    resize_avatar_file at all; it 400s here, not with a 500 from a
    downstream PIL.UnidentifiedImageError."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    not_an_image = SimpleUploadedFile("shell.php", b"<?php system($_GET['c']); ?>", content_type="image/png")

    response = auth_client.patch("/api/profile/", {"avatar": not_an_image}, format="multipart")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "avatar" in response.data

    from users.models import Profile
    profile = Profile.objects.filter(user=test_user).first()
    assert not profile or not profile.avatar

@pytest.mark.django_db
def test_change_password_wrong_current_password(auth_client, test_user):
    response = auth_client.post(
        "/api/profile/change-password/",
        {"current_password": "WrongPassword!", "new_password": "BrandNewPass123!"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    test_user.refresh_from_db()
    assert test_user.check_password("TestPass123!")

@pytest.mark.django_db
def test_change_password_success(auth_client, test_user):
    response = auth_client.post(
        "/api/profile/change-password/",
        {"current_password": "TestPass123!", "new_password": "BrandNewPass123!"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    test_user.refresh_from_db()
    assert test_user.check_password("BrandNewPass123!")
    assert not test_user.check_password("TestPass123!")

@pytest.mark.django_db
def test_change_password_revokes_outstanding_refresh_tokens(api_client, test_user):
    """A refresh token issued before the password change must be unusable
    afterward -- otherwise a stolen token survives the very event meant to
    lock an attacker out."""
    login_response = api_client.post(
        "/api/login/", {"email": test_user.email, "password": "TestPass123!"}, format="json"
    )
    stolen_refresh = login_response.cookies[REFRESH_COOKIE_NAME].value
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

    response = api_client.post(
        "/api/profile/change-password/",
        {"current_password": "TestPass123!", "new_password": "BrandNewPass123!"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.cookies[REFRESH_COOKIE_NAME].value == ""

    with pytest.raises(TokenError):
        RefreshToken(stolen_refresh)

@pytest.mark.django_db
def test_change_password_unauthenticated(api_client):
    response = api_client.post(
        "/api/profile/change-password/",
        {"current_password": "TestPass123!", "new_password": "BrandNewPass123!"},
        format="json"
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_login_is_rate_limited_after_repeated_attempts(api_client):
    for _ in range(10):
        response = api_client.post(
            "/api/login/",
            {"email": "nobody@example.com", "password": "wrong"},
            format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    throttled = api_client.post(
        "/api/login/",
        {"email": "nobody@example.com", "password": "wrong"},
        format="json"
    )
    assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS

@pytest.mark.django_db
def test_login_rejects_unverified_account_with_helpful_message(api_client):
    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Carl", email="carl@example.com"),
        format="json"
    )

    response = api_client.post(
        "/api/login/",
        {"email": "carl@example.com", "password": "SecurePassword123!"},
        format="json"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "verify" in response.data["detail"].lower()

@pytest.mark.django_db
def test_login_rejects_unverified_account_with_wrong_password_generically(api_client):
    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Carl", email="carl2@example.com"),
        format="json"
    )

    response = api_client.post(
        "/api/login/",
        {"email": "carl2@example.com", "password": "TotallyWrongPassword!"},
        format="json"
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["detail"] == "Invalid credentials."

@pytest.mark.django_db
def test_verify_email_otp_activates_account_and_logs_in(api_client, monkeypatch):
    monkeypatch.setattr("users.otp.generate_otp_code", lambda: "123456")

    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Dana", email="dana@example.com"),
        format="json"
    )
    user = User.objects.get(email="dana@example.com")
    assert user.is_active is False

    response = api_client.post(
        "/api/verify-email/",
        {"email": "dana@example.com", "otp": "123456"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert_issues_refresh_cookie(response)

    user.refresh_from_db()
    assert user.is_active is True

    login_response = api_client.post(
        "/api/login/",
        {"email": "dana@example.com", "password": "SecurePassword123!"},
        format="json"
    )
    assert login_response.status_code == status.HTTP_200_OK

@pytest.mark.django_db
def test_verify_email_otp_rejects_wrong_code(api_client, monkeypatch):
    monkeypatch.setattr("users.otp.generate_otp_code", lambda: "123456")

    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Fay", email="fay@example.com"),
        format="json"
    )

    response = api_client.post(
        "/api/verify-email/",
        {"email": "fay@example.com", "otp": "000000"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    user = User.objects.get(email="fay@example.com")
    assert user.is_active is False

@pytest.mark.django_db
def test_verify_email_otp_rejects_expired_code(api_client, monkeypatch):
    from users.models import EmailOTP

    monkeypatch.setattr("users.otp.generate_otp_code", lambda: "123456")

    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Gus", email="gus@example.com"),
        format="json"
    )
    user = User.objects.get(email="gus@example.com")
    EmailOTP.objects.filter(user=user).update(expires_at=timezone.now() - timedelta(seconds=1))

    response = api_client.post(
        "/api/verify-email/",
        {"email": "gus@example.com", "otp": "123456"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_verify_email_otp_locks_after_too_many_attempts(api_client, monkeypatch):
    monkeypatch.setattr("users.otp.generate_otp_code", lambda: "123456")

    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Hank", email="hank@example.com"),
        format="json"
    )

    for _ in range(5):
        response = api_client.post(
            "/api/verify-email/",
            {"email": "hank@example.com", "otp": "000000"},
            format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Even the correct code is now rejected -- must request a new one.
    response = api_client.post(
        "/api/verify-email/",
        {"email": "hank@example.com", "otp": "123456"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "new code" in response.data["detail"].lower()

@pytest.mark.django_db
def test_resend_email_verification_sends_new_code_once_cooldown_elapses(api_client):
    from users.models import EmailOTP

    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Eve", email="eve@example.com"),
        format="json"
    )
    assert len(mail.outbox) == 1

    user = User.objects.get(email="eve@example.com")
    EmailOTP.objects.filter(user=user).update(last_sent_at=timezone.now() - timedelta(seconds=61))

    response = api_client.post(
        "/api/verify-email/resend/",
        {"email": "eve@example.com"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 2

@pytest.mark.django_db
def test_resend_email_verification_locks_out_after_two_sends_in_a_cycle(api_client):
    from users.models import EmailOTP

    # Send #1 -- the signup itself.
    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Jae", email="jae@example.com"),
        format="json"
    )
    assert len(mail.outbox) == 1

    user = User.objects.get(email="jae@example.com")
    EmailOTP.objects.filter(user=user).update(last_sent_at=timezone.now() - timedelta(seconds=61))

    # Send #2 -- the one resend they're allowed.
    response = api_client.post("/api/verify-email/resend/", {"email": "jae@example.com"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 2

    # A third attempt, even after the normal 60s cooldown has passed, is
    # blocked -- they've used up both sends in this cycle.
    EmailOTP.objects.filter(user=user).update(last_sent_at=timezone.now() - timedelta(seconds=61))
    response = api_client.post("/api/verify-email/resend/", {"email": "jae@example.com"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 2

@pytest.mark.django_db
def test_resend_email_verification_allows_a_new_cycle_after_lockout_elapses(api_client):
    from users.models import EmailOTP

    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Kai", email="kai@example.com"),
        format="json"
    )
    user = User.objects.get(email="kai@example.com")

    # Simulate having already used both sends 31 minutes ago.
    EmailOTP.objects.filter(user=user).update(
        send_count=2,
        last_sent_at=timezone.now() - timedelta(minutes=31),
    )

    response = api_client.post("/api/verify-email/resend/", {"email": "kai@example.com"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 2

    otp = EmailOTP.objects.get(user=user)
    assert otp.send_count == 1

@pytest.mark.django_db
def test_resend_email_verification_is_silently_skipped_within_cooldown(api_client):
    api_client.post(
        "/api/signup/",
        signup_payload(first_name="Ivy", email="ivy@example.com"),
        format="json"
    )
    assert len(mail.outbox) == 1

    response = api_client.post(
        "/api/verify-email/resend/",
        {"email": "ivy@example.com"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 1

@pytest.mark.django_db
def test_resend_email_verification_generic_for_unknown_email(api_client):
    response = api_client.post(
        "/api/verify-email/resend/",
        {"email": "doesnotexist@example.com"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 0

@pytest.mark.django_db
def test_resend_email_verification_generic_for_already_verified_account(api_client, test_user):
    response = api_client.post(
        "/api/verify-email/resend/",
        {"email": test_user.email},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 0
