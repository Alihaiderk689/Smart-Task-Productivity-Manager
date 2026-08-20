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


def test_reminder_sweep_is_registered_in_beat_schedule_for_local_dev():
    from config.celery import app

    entry = app.conf.beat_schedule["process-due-reminders"]
    assert entry["task"] == "notifications.tasks.process_due_reminders_task"


def test_daily_reminder_task_is_configured_to_retry():
    # The one-shot per-task reminders (30min/5min/progress/overdue) used to
    # be Celery tasks with their own autoretry_for/max_retries policy --
    # they're plain functions now (see notifications/tasks.py's module
    # comment), since retries are handled by notifications/reminder_processor.py's
    # own attempts/PENDING-requeue mechanism instead (see
    # test_transient_error_requeues_then_fails_after_max_attempts in
    # notifications/test_reminder_processor.py). send_daily_progress_reminders
    # is unrelated to that refactor and still is a genuine Celery Beat task.
    from notifications import tasks

    task = tasks.send_daily_progress_reminders
    assert task.max_retries == 3
    assert task.retry_backoff is True
    assert task.autoretry_for == (Exception,)


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
