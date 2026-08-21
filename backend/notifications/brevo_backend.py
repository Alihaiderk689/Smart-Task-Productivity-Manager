"""Django email backend that sends through the Brevo (formerly Sendinblue)
transactional email HTTP API instead of SMTP -- see BREVO_API_KEY in
config/settings.py. Plain `requests` rather than Brevo's official
`sib-api-v3-sdk` on purpose: that SDK is a large Swagger-generated client
(Configuration/ApiClient/model classes) for what is, underneath, a single
JSON POST endpoint -- not worth the dependency weight here.

This is a drop-in EMAIL_BACKEND (see config/settings.py), not a new call
API: notifications/email_service.py still calls Django's send_mail()
unchanged, so every existing call site, and the request-time behavior
Django's test runner already provides (mail.outbox via the locmem backend
during tests), keeps working exactly as before.
"""
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoAPIError(Exception):
    """Raised for any failure sending through Brevo's API -- a non-2xx
    response or a network-level failure alike, so callers (see
    notifications/reminder_processor.py's EMAIL_TRANSIENT_ERRORS) can
    treat "the send didn't go through" uniformly, the same role
    smtplib.SMTPException played for the old SMTP backend."""


def _address(value):
    """Splits a plain email or an "email.utils"-style "Name <email>"
    string into Brevo's {"email": ..., "name": ...} shape. Django's
    EmailMessage.to/cc/bcc/from_email are plain strings, not objects, so
    this is the only place that shape conversion happens."""
    name, email = parseaddr(value)
    return {"email": email, "name": name} if name else {"email": email}


class BrevoEmailBackend(BaseEmailBackend):

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

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
        payload = {
            "sender": _address(message.from_email),
            "to": [_address(addr) for addr in message.to],
            "subject": message.subject,
            "textContent": message.body,
        }

        # send_mail(..., html_message=...) attaches the HTML part via
        # EmailMultiAlternatives.attach_alternative(html, "text/html") --
        # that's the only alternative content type this app ever sends.
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                payload["htmlContent"] = content
                break

        if message.cc:
            payload["cc"] = [_address(addr) for addr in message.cc]
        if message.bcc:
            payload["bcc"] = [_address(addr) for addr in message.bcc]
        if message.reply_to:
            # Brevo's schema takes a single replyTo object, unlike
            # Django's reply_to list -- this app never actually sets more
            # than one, so using the first is a safe simplification.
            payload["replyTo"] = _address(message.reply_to[0])

        try:
            response = requests.post(
                BREVO_SEND_URL,
                json=payload,
                headers={
                    "api-key": settings.BREVO_API_KEY,
                    "content-type": "application/json",
                    "accept": "application/json",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise BrevoAPIError(f"Request to Brevo failed: {exc}") from exc

        if not response.ok:
            raise BrevoAPIError(
                f"Brevo API returned {response.status_code}: {response.text[:500]}"
            )
