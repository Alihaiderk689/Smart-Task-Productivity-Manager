"""Centralized field-validation rules shared across the signup/login/password
serializers, so a rule only ever lives in one place (see users/serializers.py
for where these get wired up). Mirrored on the frontend in
frontend/src/lib/validation.js -- keep the two in sync."""

import re

from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

FULL_NAME_MIN_LENGTH = 2
FULL_NAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
EMAIL_MAX_LENGTH = 254

# Letters, spaces, hyphens, apostrophes only -- must start with a letter so
# " - " or "''" alone can't slip through.
FULL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z '-]*$")
_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9\s]")


def validate_full_name(value):
    """Trims and validates a full name. Returns the trimmed value or raises
    serializers.ValidationError."""
    value = (value or "").strip()

    if not value:
        raise serializers.ValidationError("Full name is required.")
    if len(value) < FULL_NAME_MIN_LENGTH:
        raise serializers.ValidationError(f"Full name must be at least {FULL_NAME_MIN_LENGTH} characters.")
    if len(value) > FULL_NAME_MAX_LENGTH:
        raise serializers.ValidationError(f"Full name cannot exceed {FULL_NAME_MAX_LENGTH} characters.")
    if not FULL_NAME_RE.match(value):
        raise serializers.ValidationError("Full name can only contain letters, spaces, hyphens, and apostrophes.")

    return value


def normalize_email(value):
    """Trims and lowercases an email, enforcing the max length. Uniqueness
    is checked separately (callers know whether they're excluding the
    current user, e.g. on profile update)."""
    value = (value or "").strip().lower()

    if len(value) > EMAIL_MAX_LENGTH:
        raise serializers.ValidationError(f"Email cannot exceed {EMAIL_MAX_LENGTH} characters.")

    return value


def validate_password_complexity(value, *, email=None):
    """Validates password strength/format rules, then runs Django's
    AUTH_PASSWORD_VALIDATORS (length, common-password, etc. -- see
    config/settings.py). Returns the value unchanged or raises
    serializers.ValidationError."""
    if len(value) < PASSWORD_MIN_LENGTH:
        raise serializers.ValidationError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise serializers.ValidationError(f"Password cannot exceed {PASSWORD_MAX_LENGTH} characters.")
    if re.search(r"\s", value):
        raise serializers.ValidationError("Password cannot contain spaces.")
    if not _UPPER_RE.search(value):
        raise serializers.ValidationError("Password must contain at least one uppercase letter.")
    if not _LOWER_RE.search(value):
        raise serializers.ValidationError("Password must contain at least one lowercase letter.")
    if not _DIGIT_RE.search(value):
        raise serializers.ValidationError("Password must contain at least one number.")
    if not _SPECIAL_RE.search(value):
        raise serializers.ValidationError("Password must contain at least one special character.")
    if email and value.strip().lower() == email.strip().lower():
        raise serializers.ValidationError("Password cannot be the same as your email.")

    try:
        django_validate_password(value)
    except DjangoValidationError as e:
        raise serializers.ValidationError(list(e.messages))

    return value
