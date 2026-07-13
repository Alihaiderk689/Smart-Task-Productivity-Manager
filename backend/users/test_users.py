import pytest
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

@pytest.mark.django_db
def test_signup_success(api_client):
    response = api_client.post(
        "/api/signup/",
        {
            "first_name": "Alice",
            "email": "alice@example.com",
            "password": "SecurePassword123!"
        },
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["user"]["email"] == "alice@example.com"
    assert User.objects.filter(email="alice@example.com").exists()

@pytest.mark.django_db
def test_signup_seeds_default_categories(api_client):
    from categories.models import Category
    from categories.services import DEFAULT_CATEGORY_NAMES

    response = api_client.post(
        "/api/signup/",
        {
            "first_name": "Bob",
            "email": "bob@example.com",
            "password": "SecurePassword123!"
        },
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

@pytest.mark.django_db
def test_signup_duplicate_email(api_client, test_user):
    response = api_client.post(
        "/api/signup/",
        {
            "first_name": "Another",
            "email": test_user.email,
            "password": "SecurePassword123!"
        },
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "Email already exists."

@pytest.mark.django_db
def test_signup_password_too_short(api_client):
    response = api_client.post(
        "/api/signup/",
        {
            "first_name": "Alice",
            "email": "alice@example.com",
            "password": "sh"
        },
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data

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
    assert "refresh" in response.data
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
def test_profile_authenticated(auth_client, test_user):
    response = auth_client.get("/api/profile/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == test_user.email

@pytest.mark.django_db
def test_profile_unauthenticated(api_client):
    response = api_client.get("/api/profile/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_logout_success(auth_client, test_user):
    refresh = RefreshToken.for_user(test_user)
    response = auth_client.post(
        "/api/logout/",
        {
            "refresh": str(refresh)
        },
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["detail"] == "Logout successful."

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

    test_user.refresh_from_db()
    assert test_user.check_password("BrandNewPass123!")

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
