import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .models import EmailOTP

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5

# A user gets at most 2 codes per cycle (the original send + 1 resend)
# before the resend button locks out for RESEND_LOCKOUT -- prevents someone
# from hammering "resend" and spamming a mailbox (or an inbox that isn't
# theirs). The cycle resets once RESEND_LOCKOUT has fully elapsed.
MAX_SENDS_PER_CYCLE = 2
RESEND_LOCKOUT = timedelta(minutes=30)


def generate_otp_code():
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def issue_otp(user, *, respect_cooldown=False):
    """Create/replace the user's verification code and return the plaintext
    code to email them. Returns None if respect_cooldown is set and sending
    is currently blocked -- either the normal RESEND_COOLDOWN between sends,
    or MAX_SENDS_PER_CYCLE has been reached and RESEND_LOCKOUT hasn't
    elapsed yet (used by "resend")."""
    otp = EmailOTP.objects.filter(user=user).first()
    now = timezone.now()

    if otp is not None and now - otp.last_sent_at >= RESEND_LOCKOUT:
        # Lockout window has fully elapsed since the last send -- start a
        # fresh cycle instead of staying permanently capped.
        otp.send_count = 0

    if respect_cooldown and otp is not None:
        if otp.send_count >= MAX_SENDS_PER_CYCLE:
            return None
        if now - otp.last_sent_at < RESEND_COOLDOWN:
            return None

    if otp is None:
        otp = EmailOTP(user=user)

    code = generate_otp_code()
    otp.code_hash = make_password(code)
    otp.expires_at = now + OTP_TTL
    otp.attempts = 0
    otp.send_count += 1
    otp.save()  # last_sent_at is auto_now, stamped here
    return code


def verify_otp(user, code):
    """Returns (ok, reason). reason is a user-facing message when ok is False."""
    try:
        otp = user.email_otp
    except EmailOTP.DoesNotExist:
        return False, "No verification code was requested for this account. Request a new one."

    if otp.attempts >= MAX_ATTEMPTS:
        return False, "Too many incorrect attempts. Request a new code."

    if timezone.now() > otp.expires_at:
        return False, "This code has expired. Request a new one."

    if not check_password(code, otp.code_hash):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        return False, "Incorrect code."

    otp.delete()
    return True, None
