import logging
import smtplib
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from tasks.models import Task
from .email_service import EmailService

logger = logging.getLogger(__name__)

# Tasks spanning longer than this get a daily check-in email (see
# send_daily_progress_reminders below) instead of just the one-shot
# reminders. Shorter tasks are already fully covered by those.
LONG_TASK_THRESHOLD = timedelta(days=1)

# Transient failures worth retrying an email send for (SMTP hiccup, DNS
# blip, connection reset) -- deliberately not a bare `Exception`, so a real
# bug in our own code fails fast and shows up in logs instead of quietly
# retrying 3 times and burying the traceback.
EMAIL_TRANSIENT_ERRORS = (smtplib.SMTPException, ConnectionError, TimeoutError, OSError)

# Shared retry policy for the one-shot per-task reminders below: back off
# exponentially, cap the wait, give up after 3 attempts (the 4th failure is
# logged and the reminder is lost -- there's no 4th automatic attempt).
RETRY_KWARGS = dict(
    autoretry_for=EMAIL_TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)


@shared_task(**RETRY_KWARGS)
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



@shared_task(**RETRY_KWARGS)
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
        update_fields = ["reminder_overdue_sent"]

        # The deadline passed without the task being completed or deliberately
        # stopped, so it's now Missed. The user can still reschedule it (see
        # reschedule_link above), which resets status back to Pending.
        if task.status not in ("Completed", "Stopped"):
            task.status = "Missed"
            update_fields.append("status")

        task.save(update_fields=update_fields)

    except Task.DoesNotExist:
        return



@shared_task(**RETRY_KWARGS)
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

@shared_task(**RETRY_KWARGS)
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


@shared_task(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=3)
def send_daily_progress_reminders():
    """Celery Beat sweep (schedule registered in config/celery.py) -- runs
    once a day and emails a check-in for every multi-day task (duration >
    LONG_TASK_THRESHOLD) that's currently active and hasn't already gotten
    today's reminder.

    Unlike the reminders above, this isn't scheduled per-task via
    apply_async(eta=...): a 5-day task needs a *recurring* nudge, not one
    fixed future instant, and the cadence (once a day) is the same for every
    task regardless of its own start/end time -- exactly the case Beat is
    for, versus apply_async's per-object one-shot scheduling.

    The task-level retry above covers a failure before/between recipients
    (e.g. the initial query). Each individual send is additionally wrapped
    in its own try/except so one user's failed email doesn't block or delay
    everyone else's in the same run -- a skipped one just gets a fresh
    attempt on tomorrow's sweep instead of tonight's retry re-processing an
    already-successful batch.
    """
    now = timezone.now()
    today = timezone.localdate()

    active_tasks = Task.objects.exclude(status__in=["Completed", "Stopped", "Missed"]).filter(
        start_time__lte=now,
        end_time__gte=now,
    )

    for task in active_tasks:
        if (task.end_time - task.start_time) <= LONG_TASK_THRESHOLD:
            continue  # short tasks are already covered by the one-shot reminders

        if task.last_daily_reminder_date == today:
            continue  # already sent today's reminder

        try:
            days_remaining = (timezone.localtime(task.end_time).date() - today).days

            EmailService.send_email(
                subject=f"'{task.title}' is still in progress",
                recipient=task.user.email,
                template_name="emails/daily_progress_reminder.html",
                context={
                    "user": task.user,
                    "task": task,
                    "days_remaining": days_remaining,
                },
            )

            task.last_daily_reminder_date = today
            task.save(update_fields=["last_daily_reminder_date"])
        except Exception:
            logger.exception("Failed to send daily progress reminder for task %s", task.id)
            continue


