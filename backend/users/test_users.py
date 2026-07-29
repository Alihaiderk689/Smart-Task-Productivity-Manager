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
    # No tokens yet -- account is inactive until the emailed link is verified.
    assert "access" not in response.data
    assert "refresh" not in response.data
    assert response.data["user"]["email"] == "alice@example.com"

    user = User.objects.get(email="alice@example.com")
    assert user.is_active is False
    assert len(mail.outbox) == 1
    assert "verify" in mail.outbox[0].subject.lower()

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
        {"first_name": "Carl", "email": "carl@example.com", "password": "SecurePassword123!"},
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
        {"first_name": "Carl", "email": "carl2@example.com", "password": "SecurePassword123!"},
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
def test_verify_email_activates_account_and_logs_in(api_client):
    from users.tokens import make_email_verification_token

    api_client.post(
        "/api/signup/",
        {"first_name": "Dana", "email": "dana@example.com", "password": "SecurePassword123!"},
        format="json"
    )
    user = User.objects.get(email="dana@example.com")
    assert user.is_active is False

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = make_email_verification_token(user)

    response = api_client.post(
        "/api/verify-email/",
        {"uid": uid, "token": token},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data

    user.refresh_from_db()
    assert user.is_active is True

    login_response = api_client.post(
        "/api/login/",
        {"email": "dana@example.com", "password": "SecurePassword123!"},
        format="json"
    )
    assert login_response.status_code == status.HTTP_200_OK

@pytest.mark.django_db
def test_verify_email_rejects_invalid_token(api_client, test_user):
    uid = urlsafe_base64_encode(force_bytes(test_user.pk))

    response = api_client.post(
        "/api/verify-email/",
        {"uid": uid, "token": "not-a-real-token"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_resend_email_verification_sends_new_link_for_unverified_account(api_client):
    api_client.post(
        "/api/signup/",
        {"first_name": "Eve", "email": "eve@example.com", "password": "SecurePassword123!"},
        format="json"
    )
    assert len(mail.outbox) == 1

    response = api_client.post(
        "/api/verify-email/resend/",
        {"email": "eve@example.com"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 2

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
