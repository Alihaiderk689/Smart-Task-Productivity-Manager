from datetime import timedelta

from django.utils import timezone

from .tasks import (
    send_30_minute_reminder,
    send_5_minute_reminder,
    send_progress_reminder,
    send_overdue_reminder,
)


class NotificationService:

    @staticmethod
    def schedule_reminders(task):
        # KNOWN GAP (documented, not fixed here -- see backend/core/views.py
        # and .github/workflows/scheduled-tasks.yml for the actual scheduler
        # hardening this task was scoped to): apply_async(eta=...) below
        # requires a live Celery worker consuming CELERY_BROKER_URL. Local
        # dev has one (`celery worker -B` + Redis, see CLAUDE.md); the
        # deployed Render environment deliberately does not (.env.render).
        # Verified directly against an unreachable broker: apply_async does
        # NOT raise (so task creation itself is safe either way), but the
        # message is never delivered -- these four one-shot reminders
        # silently never fire in production. The scheduled-task sweep does
        # NOT cover this gap: copilot.agents.reminder.ReminderAgent's
        # 15-minute "reminder_check" (run via scheduled-tasks.yml) only
        # detects a missed reminder and proposes sending it for manual
        # admin approval -- it does not auto-send. Closing this gap for
        # real (e.g. having the scheduled sweep execute missed reminders
        # automatically, or moving this scheduling onto the same sweep
        # instead of apply_async) is a deliberate product/risk decision
        # about unattended email-sending, not a mechanical fix, so it's
        # left to a follow-up rather than folded into scheduler hardening.

        version = task.reminder_version

        # 30-minute reminder
        reminder_30 = task.start_time - timedelta(minutes=30)

        if reminder_30 > timezone.now():
            send_30_minute_reminder.apply_async(
                args=[task.id, version],
                eta=reminder_30,
            )

        # 5-minute reminder
        reminder_5 = task.start_time - timedelta(minutes=5)

        if reminder_5 > timezone.now():
            send_5_minute_reminder.apply_async(
                args=[task.id, version],
                eta=reminder_5,
            )

        # Progress reminder (40% elapsed)
        duration = task.end_time - task.start_time
        progress_time = task.start_time + (duration * 0.40)

        if progress_time > timezone.now():
            send_progress_reminder.apply_async(
                args=[task.id, version],
                eta=progress_time,
            )

        # Overdue reminder
        if task.end_time > timezone.now():
            send_overdue_reminder.apply_async(
                args=[task.id, version],
                eta=task.end_time,
            )