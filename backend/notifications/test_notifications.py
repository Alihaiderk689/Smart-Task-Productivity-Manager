from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from notifications.tasks import send_daily_progress_reminders, send_overdue_reminder


@pytest.mark.django_db
def test_overdue_reminder_includes_reschedule_link(task_factory):
    task = task_factory(status="In Progress")

    send_overdue_reminder(task.id, task.reminder_version)

    assert len(mail.outbox) == 1
    body = mail.outbox[0].alternatives[0][0]
    assert f"/tasks/{task.id}?reschedule=1" in body

    task.refresh_from_db()
    assert task.reminder_overdue_sent is True
    assert task.status == "Missed"


@pytest.mark.django_db
def test_overdue_reminder_marks_pending_task_missed(task_factory):
    task = task_factory(status="Pending")

    send_overdue_reminder(task.id, task.reminder_version)

    task.refresh_from_db()
    assert task.status == "Missed"


@pytest.mark.django_db
def test_overdue_reminder_does_not_override_stopped_status(task_factory):
    task = task_factory(status="Stopped")

    send_overdue_reminder(task.id, task.reminder_version)

    assert len(mail.outbox) == 1
    task.refresh_from_db()
    assert task.status == "Stopped"


@pytest.mark.django_db
def test_overdue_reminder_skipped_when_already_sent(task_factory):
    task = task_factory(status="In Progress", reminder_overdue_sent=True)

    send_overdue_reminder(task.id, task.reminder_version)

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_overdue_reminder_skipped_for_completed_task(task_factory):
    task = task_factory(status="Completed")

    send_overdue_reminder(task.id, task.reminder_version)

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_daily_reminder_sends_for_active_multiday_task(task_factory):
    now = timezone.now()
    task = task_factory(
        status="In Progress",
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=3),
    )

    send_daily_progress_reminders()

    assert len(mail.outbox) == 1
    task.refresh_from_db()
    assert task.last_daily_reminder_date == timezone.localdate()


@pytest.mark.django_db
def test_daily_reminder_skips_short_task(task_factory):
    now = timezone.now()
    task_factory(
        status="In Progress",
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
    )

    send_daily_progress_reminders()

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_daily_reminder_skips_task_not_yet_started(task_factory):
    now = timezone.now()
    task_factory(
        status="Pending",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(days=5),
    )

    send_daily_progress_reminders()

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_daily_reminder_skips_already_ended_task(task_factory):
    now = timezone.now()
    task_factory(
        status="In Progress",
        start_time=now - timedelta(days=5),
        end_time=now - timedelta(hours=1),
    )

    send_daily_progress_reminders()

    assert len(mail.outbox) == 0


@pytest.mark.django_db
@pytest.mark.parametrize("terminal_status", ["Completed", "Stopped", "Missed"])
def test_daily_reminder_skips_terminal_statuses(task_factory, terminal_status):
    now = timezone.now()
    task_factory(
        status=terminal_status,
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=3),
    )

    send_daily_progress_reminders()

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_daily_reminder_does_not_double_send_same_day(task_factory):
    now = timezone.now()
    task = task_factory(
        status="In Progress",
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=3),
        last_daily_reminder_date=timezone.localdate(),
    )

    send_daily_progress_reminders()

    assert len(mail.outbox) == 0
    task.refresh_from_db()
    assert task.last_daily_reminder_date == timezone.localdate()


@pytest.mark.django_db
def test_daily_reminder_sends_again_on_a_new_day(task_factory):
    now = timezone.now()
    task = task_factory(
        status="In Progress",
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=3),
        last_daily_reminder_date=timezone.localdate() - timedelta(days=1),
    )

    send_daily_progress_reminders()

    assert len(mail.outbox) == 1
    task.refresh_from_db()
    assert task.last_daily_reminder_date == timezone.localdate()


def test_daily_reminder_is_registered_in_beat_schedule():
    from config.celery import app

    entry = app.conf.beat_schedule["send-daily-progress-reminders"]
    assert entry["task"] == "notifications.tasks.send_daily_progress_reminders"


@pytest.mark.parametrize(
    "task_name",
    [
        "send_5_minute_reminder",
        "send_30_minute_reminder",
        "send_progress_reminder",
        "send_overdue_reminder",
        "send_daily_progress_reminders",
    ],
)
def test_reminder_tasks_are_configured_to_retry(task_name):
    from notifications import tasks

    task = getattr(tasks, task_name)

    assert task.max_retries == 3
    assert task.retry_backoff is True
    # send_daily_progress_reminders retries on any failure (a broken query
    # affects the whole sweep); the per-task reminders only retry on
    # transient email-sending errors, not on a bug in our own code.
    if task_name == "send_daily_progress_reminders":
        assert task.autoretry_for == (Exception,)
    else:
        assert task.autoretry_for == tasks.EMAIL_TRANSIENT_ERRORS


@pytest.mark.django_db
def test_daily_reminder_one_failure_does_not_block_others(task_factory, monkeypatch):
    now = timezone.now()
    failing_task = task_factory(
        title="Failing task",
        status="In Progress",
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=3),
    )
    healthy_task = task_factory(
        title="Healthy task",
        status="In Progress",
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=3),
    )

    from notifications import tasks as notifications_tasks

    original_send_email = notifications_tasks.EmailService.send_email

    def flaky_send_email(subject, recipient, template_name, context):
        if context["task"].id == failing_task.id:
            raise TimeoutError("SMTP timed out")
        return original_send_email(subject, recipient, template_name, context)

    monkeypatch.setattr(notifications_tasks.EmailService, "send_email", staticmethod(flaky_send_email))

    send_daily_progress_reminders()

    failing_task.refresh_from_db()
    healthy_task.refresh_from_db()

    assert failing_task.last_daily_reminder_date is None
    assert healthy_task.last_daily_reminder_date == timezone.localdate()
    assert len(mail.outbox) == 1
