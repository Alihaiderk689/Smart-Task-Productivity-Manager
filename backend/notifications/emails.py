from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


class EmailService:
    @staticmethod
    def send_email(subject, recipient, template_name, context):
        html_content = render_to_string(template_name, context)

        email = EmailMultiAlternatives(
            subject=subject,
            body="",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )

        email.attach_alternative(html_content, "text/html")
        email.send()