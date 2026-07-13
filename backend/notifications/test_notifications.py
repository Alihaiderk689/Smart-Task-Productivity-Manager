import pytest
from django.core import mail

from notifications.tasks import send_overdue_reminder


@pytest.mark.django_db
def test_overdue_reminder_includes_reschedule_link(task_factory):
    task = task_factory(status="In Progress")

    send_overdue_reminder(task.id, task.reminder_version)

    assert len(mail.outbox) == 1
    body = mail.outbox[0].alternatives[0][0]
    assert f"/tasks/{task.id}?reschedule=1" in body

    task.refresh_from_db()
    assert task.reminder_overdue_sent is True


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
