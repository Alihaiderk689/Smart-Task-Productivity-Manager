from celery import shared_task
from django.conf import settings
from tasks.models import Task
from .email_service import EmailService

@shared_task
def send_5_minute_reminder(task_id, reminder_version): #this creates a celery task.

    try: #this is a try block that attempts to retrieve the task from the database using the provided task_id.
        task = Task.objects.get(id=task_id) #retrieve the task object from the database using the provided task_id.
        if task.reminder_version != reminder_version: #this helps to ensure that the reminder is set for the version, if the version has changed, and the reminder shouldnt be sent.
            return
        if task.reminder_5_sent: #this prevents duplicate reminders from being sent.
            return
        if task.status != "Pending": #only the pending tasks recieve the reminder.
            return
        EmailService.send_email(        #this sends email.
            subject="Your task starts in 5 minutes",
            recipient=task.user.email,      #gets the logged in user email.
            template_name="emails/reminder_5.html",     #html email template for the reminder.
            context={   
                "user": task.user,
                "task": task,
            },
        )

        task.reminder_5_sent = True
        task.save(update_fields=["reminder_5_sent"])

    except Task.DoesNotExist:
        return



@shared_task
def send_overdue_reminder(task_id, reminder_version):

    try:
        task = Task.objects.get(id=task_id)
        if task.reminder_version != reminder_version:
            return
        if task.reminder_overdue_sent:
            return
        if task.status == "Completed":
            return
        reschedule_link = f"{settings.FRONTEND_URL}/tasks/{task.id}?reschedule=1"
        EmailService.send_email(
            subject="Your task time has ended",
            recipient=task.user.email,
            template_name="emails/overdue_reminder.html",
            context={
                "user": task.user,
                "task": task,
                "reschedule_link": reschedule_link,
            },
        )

        task.reminder_overdue_sent = True
        task.save(update_fields=["reminder_overdue_sent"])

    except Task.DoesNotExist:
        return



@shared_task
def send_30_minute_reminder(task_id, reminder_version):
    try:
        task = Task.objects.get(id=task_id)

        # Ignore outdated scheduled reminders
        if task.reminder_version != reminder_version:
            return

        if task.reminder_30_sent:
            return

        if task.status != "Pending":
            return

        EmailService.send_email(
            subject="Your task starts in 30 minutes",
            recipient=task.user.email,
            template_name="notifications/reminder_30.html",
            context={
                "user": task.user,
                "task": task,
            },
        )

        task.reminder_30_sent = True
        task.save(update_fields=["reminder_30_sent"])

    except Task.DoesNotExist:
        return

@shared_task

def send_test_email(recipient_email):

    EmailService.send_test_email(recipient_email)

@shared_task
def send_progress_reminder(task_id, reminder_version):

    try:
        task = Task.objects.get(id=task_id)

        if task.reminder_version != reminder_version:
            return

        if task.reminder_progress_sent:
            return

        if task.status != "Pending":
            return

        EmailService.send_email(
            subject="You haven't started your task yet",
            recipient=task.user.email,
            template_name="emails/progress_reminder.html",
            context={
                "user": task.user,
                "task": task,
            },
        )

        task.reminder_progress_sent = True
        task.save(update_fields=["reminder_progress_sent"])

    except Task.DoesNotExist:
        return


