"""Django email backend that sends through the Resend HTTP API instead of
SMTP. Render blocks outbound traffic on SMTP ports (25/465/587) for free
web services, and even paid tiers are unreliable for Gmail SMTP specifically
(Gmail silently drops connections from datacenter IPs) -- Resend's API goes
out over plain HTTPS, which every host allows.

This is a drop-in EMAIL_BACKEND (see config/settings.py), not a new call
API: notifications/email_service.py still calls Django's send_mail()
unchanged, so every existing call site, and the request-time behavior
Django's test runner already provides (mail.outbox via the locmem backend
during tests), keeps working exactly as before.
"""
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

import resend


class ResendEmailBackend(BaseEmailBackend):

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        resend.api_key = settings.RESEND_API_KEY

        sent_count = 0
        for message in email_messages:
            try:
                self._send_one(message)
            except Exception:
                if not self.fail_silently:
                    raise
                continue
            sent_count += 1

        return sent_count

    @staticmethod
    def _send_one(message):
        params = {
            "from": message.from_email,
            "to": message.to,
            "subject": message.subject,
            "text": message.body,
        }

        # send_mail(..., html_message=...) attaches the HTML part via
        # EmailMultiAlternatives.attach_alternative(html, "text/html") --
        # that's the only alternative content type this app ever sends.
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                params["html"] = content
                break

        if message.cc:
            params["cc"] = message.cc
        if message.bcc:
            params["bcc"] = message.bcc
        if message.reply_to:
            params["reply_to"] = message.reply_to

        resend.Emails.send(params)
