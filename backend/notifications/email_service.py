from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


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

        send_mail(
            subject=subject,
            message="Smart Task Manager Notification",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html_message,
            fail_silently=False,
        )