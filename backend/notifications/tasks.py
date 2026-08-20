import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from tasks.models import Task
from .email_service import EmailService
from .models import Reminder
from .reminder_processor import process_due_reminders, send_reminder_now

logger = logging.getLogger(__name__)

# Tasks spanning longer than this get a daily check-in email (see
# send_daily_progress_reminders below) instead of just the one-shot
# reminders. Shorter tasks are already fully covered by those.
LONG_TASK_THRESHOLD = timedelta(days=1)


# The four functions below are thin, plain (non-Celery) wrappers kept only
# for their existing external call sites -- adminpanel/views.py's
# "trigger reminder" admin button and copilot/tools/reminder_tools.py's
# approval-gated send_reminder tool -- which both call
# func(task_id, reminder_version) directly and synchronously today. Actual
# scheduling/delivery/retry now lives in notifications/reminder_processor.py
# (database-backed, see its module docstring); these are no longer Celery
# tasks themselves since retries are handled by that module's own
# attempts/PENDING-requeue mechanism, not Celery's autoretry_for, which
# needed a live worker to ever run a retry.
def send_30_minute_reminder(task_id, reminder_version):
    send_reminder_now(task_id, reminder_version, Reminder.Kind.THIRTY_MIN)


def send_5_minute_reminder(task_id, reminder_version):
    send_reminder_now(task_id, reminder_version, Reminder.Kind.FIVE_MIN)


def send_progress_reminder(task_id, reminder_version):
    send_reminder_now(task_id, reminder_version, Reminder.Kind.PROGRESS)


def send_overdue_reminder(task_id, reminder_version):
    send_reminder_now(task_id, reminder_version, Reminder.Kind.OVERDUE)


@shared_task
def send_test_email(recipient_email):
    EmailService.send_test_email(recipient_email)


@shared_task
def process_due_reminders_task():
    """Thin Celery wrapper so local dev's Beat schedule (see
    config/celery.py) can invoke the same reminder sweep production runs
    via core/views.py::run_scheduled_tasks -- see
    notifications.reminder_processor.process_due_reminders for the actual
    claim/send/mark logic, which knows nothing about Celery at all."""
    process_due_reminders()


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


