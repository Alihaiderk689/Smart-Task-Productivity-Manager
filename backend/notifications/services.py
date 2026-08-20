import logging

from .reminder_processor import generate_reminders_for_task

logger = logging.getLogger(__name__)


class NotificationService:

    @staticmethod
    def schedule_reminders(task) -> bool:
        # Historically this queued four Celery apply_async(eta=...) jobs --
        # which required a live worker consuming CELERY_BROKER_URL and
        # silently never fired in production, since that environment
        # deliberately runs no Redis/Celery worker (see .env.render). Now
        # delegates to the database-backed reminder system (see
        # notifications/reminder_processor.py for the full design,
        # including its at-least-once delivery guarantee): this just
        # persists Reminder rows with a scheduled_for timestamp: PostgreSQL
        # (local Postgres in dev, Supabase in production -- same code
        # either way) is the source of truth a separate, later sweep reads
        # from, rather than an in-memory broker message.
        #
        # Scheduling reminders is a side effect of creating/editing a task,
        # never a precondition for it -- a task must exist regardless of
        # whether its reminders could be scheduled, so this deliberately
        # never lets an exception here escape to the caller (every call
        # site -- TaskListCreateView, TaskDetailView, reschedule_task,
        # create_repeating_tasks, and the copilot's task tools -- would
        # otherwise have to remember to guard against this individually,
        # which is exactly how a task-creation request could 500 on a
        # transient DB hiccup during reminder-row insertion despite the
        # task itself having already saved successfully). Returns whether
        # scheduling actually succeeded, for callers that want to surface
        # that (see usercopilot/tools/task_tools.py's status_note) --
        # callers that don't care can just ignore the return value.
        try:
            generate_reminders_for_task(task)
            return True
        except Exception:
            logger.exception("Failed to schedule reminders for task %s -- task itself is unaffected", task.id)
            return False
