from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self):
        return f"{self.user.email}'s profile"


class EmailOTP(models.Model):
    """A one-time code emailed to prove a signup's address is real and
    reachable (see users.otp) -- one row per user, replaced on each send."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_otp")
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField(auto_now=True)
    # How many codes have been sent in the current send cycle (see
    # users.otp.MAX_SENDS_PER_CYCLE) -- resets once RESEND_LOCKOUT has
    # elapsed since the last send.
    send_count = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"OTP for {self.user.email}"
