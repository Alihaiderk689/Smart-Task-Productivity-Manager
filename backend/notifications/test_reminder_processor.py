from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from notifications.models import Reminder
from notifications.reminder_processor import (
    MAX_ATTEMPTS,
    STALE_LEASE,
    _claim_batch,
    cancel_pending_reminders,
    generate_reminders_for_task,
    process_due_reminders,
    send_reminder_now,
)

# ---------------------------------------------------------------------------
# generate_reminders_for_task / cancel_pending_reminders
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_generate_creates_all_four_kinds_for_a_far_future_task(task_factory):
    now = timezone.now()
    task = task_factory(start_time=now + timedelta(hours=2), end_time=now + timedelta(hours=3))

    generate_reminders_for_task(task)

    kinds = set(Reminder.objects.filter(task=task).values_list("kind", flat=True))
    assert kinds == {Reminder.Kind.THIRTY_MIN, Reminder.Kind.FIVE_MIN, Reminder.Kind.PROGRESS, Reminder.Kind.OVERDUE}
    for reminder in Reminder.objects.filter(task=task):
        assert reminder.status == Reminder.Status.PENDING
        assert reminder.generation == task.reminder_version


@pytest.mark.django_db
def test_generate_skips_offsets_already_in_the_past(task_factory):
    # Starts in 1 minute: the 30-min-before and 5-min-before instants are
    # already behind us the moment this runs, so (matching the old
    # `if reminder_30 > timezone.now(): apply_async(...)` guard exactly)
    # neither should ever be scheduled.
    now = timezone.now()
    task = task_factory(start_time=now + timedelta(minutes=1), end_time=now + timedelta(hours=2))

    generate_reminders_for_task(task)

    kinds = set(Reminder.objects.filter(task=task).values_list("kind", flat=True))
    assert kinds == {Reminder.Kind.PROGRESS, Reminder.Kind.OVERDUE}


@pytest.mark.django_db
def test_regenerating_after_a_version_bump_cancels_old_generation(task_factory):
    now = timezone.now()
    task = task_factory(start_time=now + timedelta(hours=2), end_time=now + timedelta(hours=3))
    generate_reminders_for_task(task)
    old_ids = list(Reminder.objects.filter(task=task).values_list("id", flat=True))

    task.reminder_version += 1
    task.save(update_fields=["reminder_version"])
    generate_reminders_for_task(task)

    assert Reminder.objects.filter(id__in=old_ids, status=Reminder.Status.CANCELLED).count() == len(old_ids)
    new_gen = Reminder.objects.filter(task=task, generation=task.reminder_version)
    assert new_gen.count() == 4
    assert all(r.status == Reminder.Status.PENDING for r in new_gen)


@pytest.mark.django_db
def test_cancel_pending_reminders_leaves_processing_alone(task_factory):
    now = timezone.now()
    task = task_factory(start_time=now + timedelta(hours=1))
    pending = Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now, generation=task.reminder_version,
        status=Reminder.Status.PENDING,
    )
    processing = Reminder.objects.create(
        task=task, kind=Reminder.Kind.FIVE_MIN, scheduled_for=now, generation=task.reminder_version,
        status=Reminder.Status.PROCESSING, claimed_at=now,
    )

    cancel_pending_reminders(task)

    pending.refresh_from_db()
    processing.refresh_from_db()
    assert pending.status == Reminder.Status.CANCELLED
    assert processing.status == Reminder.Status.PROCESSING


# ---------------------------------------------------------------------------
# process_due_reminders / claiming
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_process_due_reminders_sends_due_and_skips_future(task_factory):
    now = timezone.now()
    task = task_factory(status="Pending", start_time=now + timedelta(minutes=40), end_time=now + timedelta(hours=2))
    due = Reminder.objects.create(
        task=task, kind=Reminder.Kind.FIVE_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=task.reminder_version,
    )
    not_due = Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now + timedelta(minutes=10),
        generation=task.reminder_version,
    )

    result = process_due_reminders()

    assert result["claimed"] == 1
    due.refresh_from_db()
    not_due.refresh_from_db()
    assert due.status == Reminder.Status.SENT
    assert not_due.status == Reminder.Status.PENDING
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_stale_generation_reminder_is_never_claimed(task_factory):
    now = timezone.now()
    task = task_factory(status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    stale = Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=task.reminder_version + 1,  # mismatched -- simulates a row left over from before a reschedule
    )

    process_due_reminders()

    stale.refresh_from_db()
    assert stale.status == Reminder.Status.PENDING
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_second_concurrent_claim_gets_nothing(task_factory):
    # Simulates two overlapping sweep runs: the second call must not see a
    # row the first already moved to PROCESSING.
    now = timezone.now()
    task = task_factory(status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=task.reminder_version,
    )

    first = _claim_batch(10)
    second = _claim_batch(10)

    assert len(first) == 1
    assert len(second) == 0


@pytest.mark.django_db
def test_stale_processing_row_is_reclaimed_and_attempt_incremented(task_factory):
    now = timezone.now()
    task = task_factory(status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    stuck = Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=30),
        generation=task.reminder_version, status=Reminder.Status.PROCESSING,
        claimed_at=now - STALE_LEASE - timedelta(minutes=1),
    )

    result = process_due_reminders()

    assert result["claimed"] == 1
    stuck.refresh_from_db()
    assert stuck.status == Reminder.Status.SENT
    assert stuck.attempts == 1  # incremented on reclaim
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_recently_claimed_processing_row_is_not_reclaimed(task_factory):
    now = timezone.now()
    task = task_factory(status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=task.reminder_version, status=Reminder.Status.PROCESSING, claimed_at=now,
    )

    result = process_due_reminders()

    assert result["claimed"] == 0
    assert len(mail.outbox) == 0


# ---------------------------------------------------------------------------
# Retry / failure handling
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_transient_error_requeues_then_fails_after_max_attempts(task_factory, monkeypatch):
    from notifications import reminder_processor

    now = timezone.now()
    task = task_factory(status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    reminder = Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=task.reminder_version,
    )

    def always_fails(*args, **kwargs):
        raise ConnectionError("SMTP unreachable")

    monkeypatch.setattr(reminder_processor.EmailService, "send_email", staticmethod(always_fails))

    for attempt in range(1, MAX_ATTEMPTS + 1):
        process_due_reminders()
        reminder.refresh_from_db()
        assert reminder.attempts == attempt
        if attempt < MAX_ATTEMPTS:
            assert reminder.status == Reminder.Status.PENDING
        else:
            assert reminder.status == Reminder.Status.FAILED

    assert "SMTP unreachable" in reminder.last_error
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_non_transient_error_fails_immediately_without_retry(task_factory, monkeypatch):
    from notifications import reminder_processor

    now = timezone.now()
    task = task_factory(status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    reminder = Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=task.reminder_version,
    )

    def boom(*args, **kwargs):
        raise ValueError("template rendering bug")

    monkeypatch.setattr(reminder_processor.EmailService, "send_email", staticmethod(boom))

    process_due_reminders()

    reminder.refresh_from_db()
    assert reminder.status == Reminder.Status.FAILED
    assert reminder.attempts == 0
    assert "template rendering bug" in reminder.last_error


@pytest.mark.django_db
def test_one_failure_does_not_block_other_due_reminders(task_factory, monkeypatch):
    from notifications import reminder_processor

    now = timezone.now()
    failing_task = task_factory(
        title="Failing", status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2),
    )
    healthy_task = task_factory(
        title="Healthy", status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2),
    )
    Reminder.objects.create(
        task=failing_task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=failing_task.reminder_version,
    )
    healthy_reminder = Reminder.objects.create(
        task=healthy_task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=healthy_task.reminder_version,
    )

    original = reminder_processor.EmailService.send_email

    def flaky(subject, recipient, template_name, context):
        if context["task"].id == failing_task.id:
            raise TimeoutError("SMTP timed out")
        return original(subject, recipient, template_name, context)

    monkeypatch.setattr(reminder_processor.EmailService, "send_email", staticmethod(flaky))

    process_due_reminders()

    healthy_reminder.refresh_from_db()
    assert healthy_reminder.status == Reminder.Status.SENT
    assert len(mail.outbox) == 1


# ---------------------------------------------------------------------------
# Eligibility / task-status interaction
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ineligible_task_status_cancels_the_reminder(task_factory):
    now = timezone.now()
    # Not Pending -- the 30-min-before reminder is only for tasks still
    # waiting to start.
    task = task_factory(status="In Progress", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    reminder = Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=now - timedelta(minutes=1),
        generation=task.reminder_version,
    )

    process_due_reminders()

    reminder.refresh_from_db()
    assert reminder.status == Reminder.Status.CANCELLED
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_overdue_reminder_marks_pending_task_missed(task_factory):
    now = timezone.now()
    task = task_factory(status="Pending", end_time=now - timedelta(minutes=1))
    Reminder.objects.create(
        task=task, kind=Reminder.Kind.OVERDUE, scheduled_for=task.end_time, generation=task.reminder_version,
    )

    process_due_reminders()

    task.refresh_from_db()
    assert task.status == "Missed"
    assert task.reminder_overdue_sent is True
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_overdue_reminder_does_not_override_stopped_status(task_factory):
    now = timezone.now()
    task = task_factory(status="Stopped", end_time=now - timedelta(minutes=1))
    Reminder.objects.create(
        task=task, kind=Reminder.Kind.OVERDUE, scheduled_for=task.end_time, generation=task.reminder_version,
    )

    process_due_reminders()

    task.refresh_from_db()
    assert task.status == "Stopped"
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_overdue_reminder_skipped_for_completed_task(task_factory):
    now = timezone.now()
    task = task_factory(status="Completed", end_time=now - timedelta(minutes=1))
    reminder = Reminder.objects.create(
        task=task, kind=Reminder.Kind.OVERDUE, scheduled_for=task.end_time, generation=task.reminder_version,
    )

    process_due_reminders()

    reminder.refresh_from_db()
    assert reminder.status == Reminder.Status.CANCELLED
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_overdue_reminder_includes_reschedule_link(task_factory):
    now = timezone.now()
    task = task_factory(status="In Progress", end_time=now - timedelta(minutes=1))
    Reminder.objects.create(
        task=task, kind=Reminder.Kind.OVERDUE, scheduled_for=task.end_time, generation=task.reminder_version,
    )

    process_due_reminders()

    assert len(mail.outbox) == 1
    body = mail.outbox[0].alternatives[0][0]
    assert f"/tasks/{task.id}?reschedule=1" in body


# ---------------------------------------------------------------------------
# send_reminder_now (manual trigger -- adminpanel button, copilot tool)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_send_reminder_now_creates_row_on_demand_when_missing(task_factory):
    now = timezone.now()
    # end_time already passed -- generate_reminders_for_task would never
    # have scheduled this one automatically (offset already in the past),
    # but a manual trigger should still be able to force it.
    task = task_factory(status="Pending", end_time=now - timedelta(minutes=5))
    assert not Reminder.objects.filter(task=task).exists()

    sent = send_reminder_now(task.id, task.reminder_version, Reminder.Kind.OVERDUE)

    assert sent is True
    assert Reminder.objects.filter(task=task, kind=Reminder.Kind.OVERDUE, status=Reminder.Status.SENT).exists()
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_send_reminder_now_rejects_stale_generation(task_factory):
    task = task_factory(status="Pending", end_time=timezone.now() - timedelta(minutes=5))

    sent = send_reminder_now(task.id, task.reminder_version + 1, Reminder.Kind.OVERDUE)

    assert sent is False
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_send_reminder_now_is_noop_once_already_sent(task_factory):
    task = task_factory(status="Pending", end_time=timezone.now() - timedelta(minutes=5))
    Reminder.objects.create(
        task=task, kind=Reminder.Kind.OVERDUE, scheduled_for=task.end_time,
        generation=task.reminder_version, status=Reminder.Status.SENT, sent_at=timezone.now(),
    )

    sent = send_reminder_now(task.id, task.reminder_version, Reminder.Kind.OVERDUE)

    assert sent is False
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_send_reminder_now_unknown_task_returns_false():
    assert send_reminder_now(999999, 1, Reminder.Kind.OVERDUE) is False


# ---------------------------------------------------------------------------
# Deletion / timezone handling
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_deleting_task_cascades_to_its_reminders(task_factory):
    now = timezone.now()
    task = task_factory(start_time=now + timedelta(hours=2), end_time=now + timedelta(hours=3))
    generate_reminders_for_task(task)
    assert Reminder.objects.filter(task=task).count() == 4

    task.delete()

    assert Reminder.objects.filter(task_id=task.id).count() == 0


@pytest.mark.django_db
def test_offsets_are_computed_against_tz_aware_datetimes(task_factory):
    import zoneinfo

    # start_time given in a non-UTC, non-server-local zone -- Django
    # normalizes any aware datetime to UTC in the DB regardless of
    # TIME_ZONE, so the offsets below must come out exactly right
    # irrespective of which zone the input happened to be expressed in.
    tokyo = zoneinfo.ZoneInfo("Asia/Tokyo")
    start = timezone.now().astimezone(tokyo) + timedelta(hours=2)
    end = start + timedelta(hours=1)
    task = task_factory(start_time=start, end_time=end)

    generate_reminders_for_task(task)

    by_kind = {r.kind: r.scheduled_for for r in Reminder.objects.filter(task=task)}
    assert by_kind[Reminder.Kind.THIRTY_MIN] == task.start_time - timedelta(minutes=30)
    assert by_kind[Reminder.Kind.FIVE_MIN] == task.start_time - timedelta(minutes=5)
    assert by_kind[Reminder.Kind.PROGRESS] == task.start_time + (task.end_time - task.start_time) * 0.40
    assert by_kind[Reminder.Kind.OVERDUE] == task.end_time
