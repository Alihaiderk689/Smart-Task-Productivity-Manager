from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

# Independent from PASSWORD_RESET_TIMEOUT (which default_token_generator uses
# for password-reset links) -- verification links need a much longer window
# since there's no urgency/security reason to expire them in minutes.
EMAIL_VERIFICATION_MAX_AGE = 60 * 60 * 24 * 3  # 3 days

_signer = TimestampSigner(salt="users.email-verification")


def make_email_verification_token(user):
    return _signer.sign(str(user.pk))


def check_email_verification_token(user, token):
    try:
        value = _signer.unsign(token, max_age=EMAIL_VERIFICATION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return value == str(user.pk)
