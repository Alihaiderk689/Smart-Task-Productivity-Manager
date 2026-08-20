from .reminder_processor import generate_reminders_for_task


class NotificationService:

    @staticmethod
    def schedule_reminders(task):
        # Historically this queued four Celery apply_async(eta=...) jobs --
        # which required a live worker consuming CELERY_BROKER_URL and
        # silently never fired in production, since that environment
        # deliberately runs no Redis/Celery worker (see .env.render). Now
        # delegates to the database-backed reminder system (see
        # notifications/reminder_processor.py for the full design,
        # including its at-least-once delivery guarantee): this just
        # persists Reminder rows with a scheduled_for timestamp: PostgreSQL
        # (local Postgres in dev, Supabase in production -- same code
        # either way) is the source of truth a periodic sweep reads from,
        # rather than an in-memory broker message.
        generate_reminders_for_task(task)
