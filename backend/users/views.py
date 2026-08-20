import logging

from django.conf import settings
from django.contrib.auth import authenticate #works like a security guard.
from django.contrib.auth.models import User #It represents the auth_user table.
from django.contrib.auth.tokens import default_token_generator
from django.db import IntegrityError
from django.http import JsonResponse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes #without permission_classes, the api_view will not work.
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from categories.services import create_default_categories
from notifications.email_service import EmailService

from .imaging import resize_avatar_file
from .models import Profile
from .otp import issue_otp, verify_otp
from .serializers import (
    ChangePasswordSerializer,
    EmailOTPVerifySerializer,
    PasswordResetConfirmSerializer,
    ProfileUpdateSerializer,
    UserSerializer,
)
from .throttling import AuthRateThrottle
from .token_cookies import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    issue_tokens,
    revoke_all_outstanding_tokens,
    set_refresh_cookie,
)

logger = logging.getLogger(__name__)


def hello(request):
    return JsonResponse({
        "message": "Hello from Django!"
    })


def _send_otp_email(user, code):
    """Best-effort: the account/OTP already exist in the DB by the time this
    runs, so a transient SMTP failure (bad/missing EMAIL_* env vars, provider
    hiccup) shouldn't 500 the whole signup/resend request -- just log it so
    it's visible, and let the user retry via the resend-verification flow."""
    try:
        EmailService.send_email(
            subject="Your Smart Task Manager verification code",
            recipient=user.email,
            template_name="emails/verify_email_otp.html",
            context={"user": user, "code": code},
        )
    except Exception:
        logger.exception("Failed to send OTP email to user_id=%s email=%r", user.id, user.email)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def signup(request):
    serializer = UserSerializer(data=request.data)

    if not serializer.is_valid():
        logger.warning(
            "Signup rejected for email=%r: %s",
            request.data.get("email"), serializer.errors,
        )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = serializer.save()
    except IntegrityError:
        # The pre-save uniqueness check in validate_email() already catches
        # the common case -- this is only a safety net for the rare race
        # where two signups for the same email land at nearly the same time.
        logger.warning(
            "Signup race: email=%r already existed by the time it was saved",
            serializer.validated_data.get("email"),
        )
        return Response(
            {"email": ["This email is already registered."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    create_default_categories(user)
    code = issue_otp(user)
    _send_otp_email(user, code)
    logger.info("New account created: user_id=%s email=%r", user.id, user.email)

    return Response(
        {
            "message": "Account created! Enter the verification code we emailed you to activate your account.",
            "user": {"id": user.id, "first_name": user.first_name, "email": user.email, "is_staff": user.is_staff},
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def login(request):
    # Signup always normalizes and stores email/username as lowercase (see
    # UserSerializer.validate_email) -- normalize here too so login isn't
    # case-sensitive on an address the user typed differently than at signup.
    # (Plain strip/lower, not validators.normalize_email -- that also
    # enforces the 254-char signup limit, which login shouldn't reject on.)
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password")

    if not email or not password:
        logger.info("Login rejected: missing email or password")
        return Response({"detail": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    # Resolve the actual stored username via a case-insensitive lookup first
    # -- covers any pre-existing account whose email/username predates
    # lowercase normalization (see the 0006 data migration), where a direct
    # authenticate(username=email, ...) would otherwise miss a case mismatch.
    matched_user = User.objects.filter(email__iexact=email).first()
    username_to_authenticate = matched_user.username if matched_user else email
    user = authenticate(request, username=username_to_authenticate, password=password)

    if user is None:
        # authenticate() returns None for inactive (unverified) accounts too,
        # even with the correct password -- check_password lets us tell them
        # why, without revealing anything to someone just guessing passwords.
        unverified = User.objects.filter(email=email, is_active=False).first()
        if unverified is not None and unverified.check_password(password):
            logger.info("Login blocked: email=%r has not verified yet", email)
            return Response(
                {"detail": "Please verify your email before logging in. Check your inbox for the verification code."},
                status=status.HTTP_403_FORBIDDEN,
            )
        logger.info("Login failed: invalid credentials for email=%r", email)
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    response = Response(
        {"user": {"id": user.id, "first_name": user.first_name, "email": user.email, "is_staff": user.is_staff}}
    )
    response.data["access"] = issue_tokens(response, user)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def google_login(request):
    """Exchange a Google ID token (from the frontend's "Sign in with Google"
    button) for our own JWT pair, creating the account on first login."""
    credential = request.data.get("credential")
    if not credential:
        return Response({"detail": "Google credential is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not settings.GOOGLE_CLIENT_ID:
        return Response({"detail": "Google sign-in is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        payload = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError:
        # Malformed/expired/wrong-audience token -- the credential itself is bad.
        return Response({"detail": "Invalid Google credential."}, status=status.HTTP_401_UNAUTHORIZED)
    except GoogleAuthError:
        # verify_oauth2_token() fetches Google's signing certs over HTTPS --
        # a transient network/transport failure reaching Google raises this
        # (not ValueError), so without this handler it fell through to a
        # generic 500. It's not the user's fault, so make that distinction.
        logger.exception("Google auth transport error while verifying credential")
        return Response(
            {"detail": "Couldn't reach Google to verify your sign-in. Please try again."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    email = (payload.get("email") or "").strip().lower()
    if not email or not payload.get("email_verified"):
        return Response({"detail": "Google account email is not verified."}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.filter(email__iexact=email).first()

    if user is None:
        # password=None gives the account an unusable password -- they can
        # only ever sign in via Google unless they later set one.
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=payload.get("given_name", ""),
            password=None,
            is_active=True,  # Google already verified this email address
        )
        create_default_categories(user)
    elif not user.is_active:
        # They'd signed up with email/password but never verified -- Google
        # just proved they own the address, so unblock the account. The
        # existing password was set by whoever created this account, which
        # is not necessarily the person who just proved ownership via
        # Google (an attacker can pre-register someone else's email with a
        # password only the attacker knows, then wait for the real owner
        # to "Sign in with Google") -- so it must be invalidated here
        # rather than trusted, exactly like a fresh Google-only signup
        # (see SECURITY.md's OAuth account-linking gap).
        user.is_active = True
        user.set_unusable_password()
        user.save(update_fields=["is_active", "password"])

    response = Response(
        {"user": {"id": user.id, "first_name": user.first_name, "email": user.email, "is_staff": user.is_staff}}
    )
    response.data["access"] = issue_tokens(response, user)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def verify_email_otp(request):
    serializer = EmailOTPVerifySerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data["email"]
    code = serializer.validated_data["otp"]

    user = User.objects.filter(email=email, is_active=False).first()
    if user is None:
        return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

    ok, reason = verify_otp(user, code)
    if not ok:
        return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)

    user.is_active = True
    user.save(update_fields=["is_active"])

    # Log the user straight into their account now that it's verified.
    response = Response(
        {
            "detail": "Email verified successfully.",
            "user": {"id": user.id, "first_name": user.first_name, "email": user.email, "is_staff": user.is_staff},
        },
        status=status.HTTP_200_OK,
    )
    response.data["access"] = issue_tokens(response, user)
    return response


GENERIC_VERIFICATION_RESEND_MESSAGE = "If an account exists for that email and still needs verification, a new code has been sent."


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def resend_email_verification(request):
    """Always returns a generic message so we don't reveal whether a given
    email address has an account (matches request_password_reset). Silently
    no-ops if a code was already sent within the last minute."""
    email = request.data.get("email")

    if not email:
        return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=email, is_active=False).first()

    if user is not None:
        code = issue_otp(user, respect_cooldown=True)
        if code is not None:
            _send_otp_email(user, code)

    return Response({"detail": GENERIC_VERIFICATION_RESEND_MESSAGE}, status=status.HTTP_200_OK)


def _serialize_profile(request, user):
    profile_obj, _ = Profile.objects.get_or_create(user=user)
    avatar_url = request.build_absolute_uri(profile_obj.avatar.url) if profile_obj.avatar else None
    return {
        "id": user.id,
        "first_name": user.first_name,
        "email": user.email,
        "avatar": avatar_url,
        "is_staff": user.is_staff,
    }


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def profile(request):
    # Protected endpoint: requires JWT in Authorization header
    if not request.user or not request.user.is_authenticated:
        return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

    user = request.user

    if request.method == "GET":
        return Response(_serialize_profile(request, user))

    serializer = ProfileUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile_obj, _ = Profile.objects.get_or_create(user=user)

    if "first_name" in serializer.validated_data:
        user.first_name = serializer.validated_data["first_name"]
        user.save(update_fields=["first_name"])

    if "avatar" in serializer.validated_data:
        profile_obj.avatar = resize_avatar_file(serializer.validated_data["avatar"])
        profile_obj.save(update_fields=["avatar"])

    return Response(_serialize_profile(request, user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = request.user

    if not user.check_password(serializer.validated_data["current_password"]):
        return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])

    # Blacklists every outstanding refresh token for this user, so a
    # stolen refresh token (or a session on another device) can't mint
    # any more access tokens after this. This does NOT invalidate an
    # access token still within its own lifetime -- SimpleJWT's blacklist
    # is only consulted during refresh, never on ordinary authenticated
    # requests -- which is exactly why ACCESS_TOKEN_LIFETIME is kept
    # short (config/settings.py). The current request's own session ends
    # too: the caller's refresh cookie is cleared below, so continuing to
    # use this device also requires logging back in.
    revoke_all_outstanding_tokens(user)

    response = Response({"detail": "Password changed successfully. Please sign in again."})
    clear_refresh_cookie(response)
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def logout(request):
    """Blacklist the refresh token cookie so it can no longer be used, and
    clear it. JSON-only parsing (no form/multipart) is deliberate: a
    classic cross-site <form> POST can't set Content-Type: application/json,
    so this alone -- combined with the CORS origin allowlist blocking a
    cross-origin fetch() from setting it either -- is what stops a forged
    cross-site request from riding this cookie (see SECURITY.md's CSRF
    section)."""
    # DRF only negotiates/validates the request's Content-Type against
    # parser_classes the first time request.data is actually accessed --
    # this view has no other reason to touch it, so without this line the
    # @parser_classes([JSONParser]) restriction above would silently never
    # trigger and a form-encoded body would sail through.
    _ = request.data
    token = request.COOKIES.get(REFRESH_COOKIE_NAME)

    if token:
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            pass

    response = Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)
    clear_refresh_cookie(response)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def token_refresh(request):
    """Cookie-based replacement for rest_framework_simplejwt's stock
    TokenRefreshView (which reads `refresh` from the request body -- the
    refresh token never reaches the request body or JS at all now, only
    this HttpOnly cookie). Reuses SimpleJWT's own TokenRefreshSerializer
    for the actual rotate/blacklist logic rather than reimplementing it,
    and mirrors TokenRefreshView.post()'s exact TokenError -> InvalidToken
    handling so behavior (401 on an expired/blacklisted/malformed token)
    stays identical. A *missing* token is a 400, not a 401, also
    matching the original: the stock view's serializer treats a missing
    `refresh` field as a plain required-field validation error, and this
    endpoint has to stay reachable with zero credentials by design (it's
    how a session gets its first refresh after a hard page reload with no
    access token in memory yet) -- see PUBLIC_ENDPOINTS in
    config/test_authentication_filters.py, which locks in that no public
    endpoint ever answers 401."""
    # See the matching comment in logout() -- forces DRF's parser
    # negotiation (and therefore the @parser_classes([JSONParser])
    # Content-Type check) to actually run.
    _ = request.data
    token = request.COOKIES.get(REFRESH_COOKIE_NAME)
    if not token:
        return Response({"detail": "Refresh token required."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = TokenRefreshSerializer(data={"refresh": token})
    try:
        serializer.is_valid(raise_exception=True)
    except TokenError as exc:
        raise InvalidToken(exc.args[0]) from exc

    response = Response({"access": serializer.validated_data["access"]})
    # ROTATE_REFRESH_TOKENS is on, so the serializer always returns a new
    # "refresh" value here -- the `token` fallback only matters if that
    # setting is ever turned off.
    set_refresh_cookie(response, serializer.validated_data.get("refresh", token))
    return response


GENERIC_RESET_MESSAGE = "If an account exists for that email, a password reset link has been sent."


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def request_password_reset(request):
    """Email a password reset link. Always returns a generic message so we
    don't reveal whether a given email address has an account."""
    email = request.data.get("email")

    if not email:
        return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=email).first()

    if user is not None:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

        try:
            EmailService.send_email(
                subject="Reset your Smart Task Manager password",
                recipient=user.email,
                template_name="emails/password_reset.html",
                context={"user": user, "reset_link": reset_link},
            )
        except Exception:
            logger.exception("Failed to send password reset email to user_id=%s email=%r", user.id, user.email)

    return Response({"detail": GENERIC_RESET_MESSAGE}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def confirm_password_reset(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    uid = serializer.validated_data["uid"]
    token = serializer.validated_data["token"]
    new_password = serializer.validated_data["new_password"]

    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return Response({"detail": "This reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({"detail": "This reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save(update_fields=["password"])

    # Same reasoning as change_password: whoever could reach this token was
    # sent a reset email, but the account may have been compromised (that's
    # plausibly *why* a reset was requested) -- revoke every session issued
    # before this reset, then log the user into a clean one below.
    revoke_all_outstanding_tokens(user)

    response = Response(
        {
            "detail": "Password has been reset successfully.",
            "user": {"id": user.id, "first_name": user.first_name, "email": user.email, "is_staff": user.is_staff},
        },
        status=status.HTTP_200_OK,
    )
    response.data["access"] = issue_tokens(response, user)
    return response