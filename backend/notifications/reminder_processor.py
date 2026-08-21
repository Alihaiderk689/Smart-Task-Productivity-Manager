"""Database-backed reminder scheduling and delivery -- the replacement for
the old per-task Celery `apply_async(eta=...)` scheduling, which silently
never fired in production because that environment deliberately runs no
Redis/Celery worker (see `.env.render`). PostgreSQL is now the single
source of truth for *when* each reminder is due -- the same Django models
and this same code run against local Postgres in dev and Supabase
Postgres in production (see `config/settings.py`'s `DATABASE_URL_DEV`/
`DATABASE_URL_PROD` split); there is no environment-specific reminder
logic anywhere in this module.

Delivery model: this provides AT-LEAST-ONCE delivery, not exactly-once,
and that is a deliberate choice, not an oversight. `EmailService.send_email`
is a blocking SMTP call; once it returns without raising, the mail server
has already accepted the message. If the process dies (Render restart,
OOM, a killed GitHub Actions run) between that return and the `Reminder`
row's status actually reaching SENT, the row is left at PROCESSING, and a
later sweep's stale-lease recovery (see STALE_LEASE below) will reclaim
and resend it -- a duplicate email, in the rare case of a genuine crash
mid-send. The alternative (mark SENT *before* sending, for at-most-once)
was rejected: a crash before the send actually fires would then silently
lose the reminder forever with no retry -- exactly the production failure
mode this module exists to fix. An occasional duplicate reminder email is
a minor annoyance; a silently missing one is the real product failure, so
at-least-once is the safer choice for this specific domain (it would NOT
be the right call for something like a payment charge). True exactly-once
would require an idempotency key honored by the email provider itself,
which would mean replacing the SMTP-based EmailService with a provider
API -- out of scope here.

Two things intentionally shrink the crash window and make any duplicate
traceable rather than silent:
  - the Reminder row's SENT transition is a single fast `.update()`
    executed as the very next statement after `send_email()` returns,
    with nothing else in between (see `_process_claimed` below) --
    minimizes wall-clock exposure to microseconds under normal operation.
  - reclaiming a stale PROCESSING row increments `attempts` and logs a
    distinct warning, so a resend is visible in the data/logs, not silent.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from resend.exceptions import ResendError

from tasks.models import Task

from .email_service import EmailService
from .models import Reminder

logger = logging.getLogger(__name__)

# Same transient-vs-real-bug distinction the old Celery autoretry_for used:
# a Resend API/network hiccup is worth retrying; a bug in our own code
# should fail fast and show up in logs instead of quietly retrying and
# burying the traceback. ResendError covers every failure the Resend SDK
# itself raises (HTTP errors, rate limits, and network failures alike --
# see resend/request.py, which wraps request-level exceptions into a
# ResendError too); ConnectionError/TimeoutError/OSError are kept for any
# lower-level socket error that surfaces before the SDK gets a chance to
# wrap it.
EMAIL_TRANSIENT_ERRORS = (ResendError, ConnectionError, TimeoutError, OSError)

# Retries now happen by going back to PENDING for the *next* sweep --
# naturally rate-limited by the sweep's own cadence, no busy-loop -- capped
# here so a persistently-failing send doesn't retry forever.
MAX_ATTEMPTS = 3

# How long a PROCESSING row can sit before it's treated as an orphaned
# claim (worker died mid-send) and recovered by the next sweep.
# Comfortably longer than the scheduled-tasks workflow's own
# `timeout-minutes: 12` cap and any realistic single-run duration, so a
# row still stuck past this is a strong signal something actually died,
# not routine.
STALE_LEASE = timedelta(minutes=10)


def _offsets_for(task: Task) -> dict:
    """The four fixed reminder instants for a task -- offsets/semantics
    unchanged from the old NotificationService.schedule_reminders, only
    how they're persisted and delivered."""
    duration = task.end_time - task.start_time
    return {
        Reminder.Kind.THIRTY_MIN: task.start_time - timedelta(minutes=30),
        Reminder.Kind.FIVE_MIN: task.start_time - timedelta(minutes=5),
        Reminder.Kind.PROGRESS: task.start_time + (duration * 0.40),
        Reminder.Kind.OVERDUE: task.end_time,
    }


def cancel_pending_reminders(task: Task) -> None:
    """Cancels this task's still-PENDING reminders. Deliberately leaves
    PROCESSING rows alone -- one might be mid-send right now, and letting
    it finish naturally (it'll self-transition to SENT/FAILED) is
    harmless, while cancelling out from under an in-flight claim is not
    worth the risk for what's ultimately just bookkeeping."""
    Reminder.objects.filter(task=task, status=Reminder.Status.PENDING).update(status=Reminder.Status.CANCELLED)


def generate_reminders_for_task(task: Task) -> None:
    """(Re)creates this task's reminder rows for its *current*
    start_time/end_time and reminder_version -- called on create, and on
    any edit that changes the schedule (reschedule_task, a plain
    TaskDetailView PATCH, the copilot's update_task). Safe to call
    repeatedly: existing pending rows are cancelled first, and a row is
    only created for an offset still in the future (matches the old
    `if reminder_30 > timezone.now(): apply_async(...)` guard exactly --
    an offset already in the past when this runs is simply never
    scheduled, same as before)."""
    cancel_pending_reminders(task)

    now = timezone.now()
    rows = [
        Reminder(task=task, kind=kind, scheduled_for=when, generation=task.reminder_version)
        for kind, when in _offsets_for(task).items()
        if when > now
    ]
    if rows:
        # ignore_conflicts guards against a double-call for the same
        # generation (the unique constraint on task+kind+generation) --
        # harmless no-op rather than an IntegrityError.
        Reminder.objects.bulk_create(rows, ignore_conflicts=True)


_SEND_SPECS = {
    Reminder.Kind.THIRTY_MIN: dict(
        subject="Your task starts in 30 minutes",
        template="notifications/reminder_30.html",
        task_flag="reminder_30_sent",
        eligible=lambda task: task.status == "Pending",
    ),
    Reminder.Kind.FIVE_MIN: dict(
        subject="Your task starts in 5 minutes",
        template="emails/reminder_5.html",
        task_flag="reminder_5_sent",
        eligible=lambda task: task.status == "Pending",
    ),
    Reminder.Kind.PROGRESS: dict(
        subject="You haven't started your task yet",
        template="emails/progress_reminder.html",
        task_flag="reminder_progress_sent",
        eligible=lambda task: task.status == "Pending",
    ),
    Reminder.Kind.OVERDUE: dict(
        subject="Your task time has ended",
        template="emails/overdue_reminder.html",
        task_flag="reminder_overdue_sent",
        eligible=lambda task: task.status != "Completed",
    ),
}


def _build_context(reminder: Reminder) -> dict:
    task = reminder.task
    context = {"user": task.user, "task": task}
    if reminder.kind == Reminder.Kind.OVERDUE:
        context["reschedule_link"] = f"{settings.FRONTEND_URL}/tasks/{task.id}?reschedule=1"
    return context


def _process_claimed(reminder: Reminder) -> None:
    """Sends (or appropriately resolves) one already-CLAIMED
    (status=PROCESSING) reminder and always leaves it in a stable state:
    SENT, FAILED, CANCELLED (ineligible), or back to PENDING for a
    bounded retry. Never raises -- every outcome is captured onto the row
    itself so a bad send can't take down the rest of a batch."""
    spec = _SEND_SPECS[reminder.kind]
    task = reminder.task

    if not spec["eligible"](task):
        # Terminal on purpose -- leaving this PENDING/PROCESSING would let
        # it be reclaimed and re-checked forever (task status won't
        # naturally go back to an eligible state outside of a reschedule,
        # which already regenerates reminders under a new generation).
        reminder.status = Reminder.Status.CANCELLED
        reminder.save(update_fields=["status"])
        return

    try:
        EmailService.send_email(
            subject=spec["subject"],
            recipient=task.user.email,
            template_name=spec["template"],
            context=_build_context(reminder),
        )
    except EMAIL_TRANSIENT_ERRORS as exc:
        reminder.attempts += 1
        reminder.last_error = str(exc)[:2000]
        reminder.status = Reminder.Status.FAILED if reminder.attempts >= MAX_ATTEMPTS else Reminder.Status.PENDING
        reminder.save(update_fields=["attempts", "last_error", "status"])
        return
    except Exception as exc:
        # Not one of the recognized transient errors -- likely a bug in
        # our own code rather than an SMTP hiccup, so fail fast and log
        # loudly instead of quietly retrying something retrying won't fix.
        logger.exception("Non-transient error sending reminder %s -- not retrying", reminder.id)
        reminder.status = Reminder.Status.FAILED
        reminder.last_error = str(exc)[:2000]
        reminder.save(update_fields=["status", "last_error"])
        return

    # Crash-window minimization (see module docstring): commit the
    # Reminder's SENT transition as the very next statement after the
    # send call returns, before anything else -- this is the one write
    # that actually prevents a resend, so it happens first and fast.
    Reminder.objects.filter(pk=reminder.pk).update(status=Reminder.Status.SENT, sent_at=timezone.now())

    # Denormalized Task-side bookkeeping (read by ReminderAgent and the
    # admin panel -- see copilot/tools/reminder_tools.py) -- best-effort,
    # secondary to the write above.
    task_update_fields = [spec["task_flag"]]
    setattr(task, spec["task_flag"], True)
    if reminder.kind == Reminder.Kind.OVERDUE and task.status not in ("Completed", "Stopped"):
        task.status = "Missed"
        task_update_fields.append("status")
    task.save(update_fields=task_update_fields)


@transaction.atomic
def _claim_batch(limit: int) -> list:
    now = timezone.now()
    stale_before = now - STALE_LEASE
    qs = (
        Reminder.objects.select_for_update(skip_locked=True)
        .filter(generation=F("task__reminder_version"))
        .filter(
            Q(status=Reminder.Status.PENDING, scheduled_for__lte=now)
            | Q(status=Reminder.Status.PROCESSING, claimed_at__lt=stale_before)
        )
        .select_related("task", "task__user")
        .order_by("scheduled_for")[:limit]
    )
    claimed = list(qs)
    if not claimed:
        return []

    reclaimed_ids = [r.id for r in claimed if r.status == Reminder.Status.PROCESSING]
    if reclaimed_ids:
        logger.warning(
            "Reclaiming %d reminder(s) stuck in PROCESSING past the %s stale lease -- "
            "a prior attempt may have actually sent the email; this resend could be a duplicate. ids=%s",
            len(reclaimed_ids), STALE_LEASE, reclaimed_ids,
        )
        Reminder.objects.filter(id__in=reclaimed_ids).update(attempts=F("attempts") + 1)

    claimed_at = timezone.now()
    Reminder.objects.filter(id__in=[r.id for r in claimed]).update(
        status=Reminder.Status.PROCESSING, claimed_at=claimed_at,
    )
    for r in claimed:
        r.status = Reminder.Status.PROCESSING
        r.claimed_at = claimed_at
    return claimed


def process_due_reminders(batch_size: int = 200) -> dict:
    """The periodic sweep -- called directly (no Celery/broker involved)
    by core/views.py's run-scheduled-tasks endpoint in production (via the
    dedicated 5-minute 'reminders' job group -- see
    .github/workflows/scheduled-tasks.yml) and by Celery Beat in local dev
    (see config/celery.py's process-due-reminders entry, and
    notifications.tasks.process_due_reminders_task for the thin Celery
    wrapper). Same function either way -- this app already established
    that pattern for send_daily_progress_reminders, this follows it."""
    claimed = _claim_batch(batch_size)
    for reminder in claimed:
        _process_claimed(reminder)
    return {"claimed": len(claimed)}


def _claim_one_for_manual_trigger(task_id: int, generation: int, kind: str):
    """Used by send_reminder_now below -- claims one specific reminder
    immediately, ignoring scheduled_for (an explicit human/agent decision
    to send early overrides the schedule), through the exact same
    PROCESSING-state claim as the periodic sweep so the two can never race
    each other into a double-send.

    get_or_create's own internal IntegrityError handling (it retries with
    a fresh get() if a concurrent identical get_or_create wins the insert
    race) makes this safe to call concurrently without needing
    select_for_update for the existence check itself -- select_for_update
    is reserved for the actual claim below, on a row now guaranteed to
    exist. (Combining skip_locked=True with get_or_create's own SELECT
    would be actively wrong: a row that exists but is locked by a
    concurrent claim would look like "doesn't exist" and get_or_create
    would then try to INSERT a duplicate, hitting the unique constraint.)

    Ensures a row exists even if generate_reminders_for_task never created
    one for this kind -- e.g. the offset was already in the past at
    creation time, so it was never auto-scheduled (see that function's
    "only if still in the future" guard). An explicit manual trigger
    should still be able to force a send in that case, same as the old
    Celery-task version could (nothing there depended on a job having
    ever been queued)."""
    reminder, _created = Reminder.objects.get_or_create(
        task_id=task_id, kind=kind, generation=generation,
        defaults={"scheduled_for": timezone.now()},
    )

    with transaction.atomic():
        stale_before = timezone.now() - STALE_LEASE
        row = (
            Reminder.objects.select_for_update(skip_locked=True)
            .filter(pk=reminder.pk)
            .filter(Q(status=Reminder.Status.PENDING) | Q(status=Reminder.Status.PROCESSING, claimed_at__lt=stale_before))
            .select_related("task", "task__user")
            .first()
        )
        if row is None:
            return None

        was_stale_reclaim = row.status == Reminder.Status.PROCESSING
        if was_stale_reclaim:
            logger.warning(
                "Reclaiming reminder %s stuck in PROCESSING past the stale lease for a manual trigger -- "
                "a prior attempt may have actually sent the email; this resend could be a duplicate.",
                row.id,
            )
            row.attempts += 1
        row.status = Reminder.Status.PROCESSING
        row.claimed_at = timezone.now()
        row.save(update_fields=["status", "claimed_at", "attempts"] if was_stale_reclaim else ["status", "claimed_at"])
        return row


def send_reminder_now(task_id: int, reminder_version: int, kind: str) -> bool:
    """Manual/approval-gated 'send this specific reminder right now' path
    -- used by notifications.tasks's four thin per-kind wrapper functions
    (adminpanel's trigger-reminder button, the copilot's approval-gated
    send_reminder tool). Goes through the exact same atomic claim as the
    periodic sweep, so a manual trigger firing at the same moment the
    sweep claims the same row can never both send. Returns True if this
    call actually resolved (sent, or found ineligible/ended up cancelled)
    the reminder, False if there was nothing to claim -- already sent,
    already claimed elsewhere, no such reminder, or a stale
    reminder_version (mirrors the old Celery tasks' identical guard)."""
    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return False
    if task.reminder_version != reminder_version:
        return False

    reminder = _claim_one_for_manual_trigger(task_id, reminder_version, kind)
    if reminder is None:
        return False

    _process_claimed(reminder)
    return True
