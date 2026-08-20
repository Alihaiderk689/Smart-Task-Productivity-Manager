from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags


class EmailService:

    @staticmethod
    def send_test_email(recipient_email):
        send_mail(
            subject="Smart Task Manager Test Email",
            message="Congratulations! Your email system is working correctly.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )


    @staticmethod
    def send_email(subject, recipient, template_name, context):

        html_message = render_to_string(
            template_name,
            context
        )
        # A plain-text part that doesn't match the HTML content (e.g. a
        # generic stub) is a spam-filter red flag -- it's exactly the
        # multipart pattern spam/phishing mail uses to slip past
        # text-based filters. Deriving it from the real HTML keeps the
        # two parts saying the same thing.
        plain_message = strip_tags(html_message)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html_message,
            fail_silently=False,
        )