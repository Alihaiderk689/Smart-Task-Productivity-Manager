from django.conf import settings
from django.contrib.auth import authenticate #works like a security guard.
from django.contrib.auth.models import User #It represents the auth_user table.
from django.contrib.auth.tokens import default_token_generator
from django.http import JsonResponse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes #without permission_classes, the api_view will not work.
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from categories.services import create_default_categories
from notifications.email_service import EmailService

from .models import Profile
from .serializers import (
    ChangePasswordSerializer,
    EmailVerificationConfirmSerializer,
    PasswordResetConfirmSerializer,
    ProfileUpdateSerializer,
    UserSerializer,
)
from .throttling import AuthRateThrottle
from .tokens import check_email_verification_token, make_email_verification_token


def hello(request):
    return JsonResponse({
        "message": "Hello from Django!"
    })


def _send_verification_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = make_email_verification_token(user)
    verify_link = f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}"

    EmailService.send_email(
        subject="Verify your Smart Task Manager email",
        recipient=user.email,
        template_name="emails/verify_email.html",
        context={"user": user, "verify_link": verify_link},
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def signup(request):

    # Check if email already exists
    if User.objects.filter(email=request.data.get("email")).exists():
        return Response(
            {"message": "Email already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = UserSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.save()
        create_default_categories(user)
        _send_verification_email(user)

        return Response(
            {
                "message": "Account created! Check your email to verify your account before logging in.",
                "user": {"id": user.id, "first_name": user.first_name, "email": user.email},
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def login(request):
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response({"detail": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    # authenticate using email as username (we set username=email on signup)
    user = authenticate(request, username=email, password=password)

    if user is None:
        # authenticate() returns None for inactive (unverified) accounts too,
        # even with the correct password -- check_password lets us tell them
        # why, without revealing anything to someone just guessing passwords.
        unverified = User.objects.filter(email=email, is_active=False).first()
        if unverified is not None and unverified.check_password(password):
            return Response(
                {"detail": "Please verify your email before logging in. Check your inbox for the verification link."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "user": {"id": user.id, "first_name": user.first_name, "email": user.email},
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def confirm_email_verification(request):
    serializer = EmailVerificationConfirmSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    uid = serializer.validated_data["uid"]
    token = serializer.validated_data["token"]

    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return Response({"detail": "This verification link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

    if not check_email_verification_token(user, token):
        return Response({"detail": "This verification link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])

    # Log the user straight into their account now that it's verified.
    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "detail": "Email verified successfully.",
            "user": {"id": user.id, "first_name": user.first_name, "email": user.email},
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        status=status.HTTP_200_OK,
    )


GENERIC_VERIFICATION_RESEND_MESSAGE = "If an account exists for that email and still needs verification, a new link has been sent."


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def resend_email_verification(request):
    """Always returns a generic message so we don't reveal whether a given
    email address has an account (matches request_password_reset)."""
    email = request.data.get("email")

    if not email:
        return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=email, is_active=False).first()

    if user is not None:
        _send_verification_email(user)

    return Response({"detail": GENERIC_VERIFICATION_RESEND_MESSAGE}, status=status.HTTP_200_OK)


def _serialize_profile(request, user):
    profile_obj, _ = Profile.objects.get_or_create(user=user)
    avatar_url = request.build_absolute_uri(profile_obj.avatar.url) if profile_obj.avatar else None
    return {"id": user.id, "first_name": user.first_name, "email": user.email, "avatar": avatar_url}


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
        profile_obj.avatar = serializer.validated_data["avatar"]
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

    return Response({"detail": "Password changed successfully."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """Blacklist the provided refresh token so it can no longer be used."""
    token = request.data.get("refresh")
    if not token:
        return Response({"detail": "Refresh token required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        RefreshToken(token).blacklist()
    except TokenError:
        return Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)
    except Exception:
        return Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)

    return Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)


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

        EmailService.send_email(
            subject="Reset your Smart Task Manager password",
            recipient=user.email,
            template_name="emails/password_reset.html",
            context={"user": user, "reset_link": reset_link},
        )

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

    # Log the user straight into their account after a successful reset.
    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "detail": "Password has been reset successfully.",
            "user": {"id": user.id, "first_name": user.first_name, "email": user.email},
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        status=status.HTTP_200_OK,
    )