import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

# Celery Beat schedule. Unlike the per-task reminders (scheduled individually
# via apply_async(eta=...) in notifications/services.py), this is a single
# fixed recurring job -- it runs once a day and sweeps all users' multi-day
# tasks for a check-in, which is exactly what Beat is for. Requires a
# `celery beat` process running alongside the worker (or `celery worker -B`
# for local dev) -- see notifications/tasks.py::send_daily_progress_reminders.
app.conf.beat_schedule = {
    "send-daily-progress-reminders": {
        "task": "notifications.tasks.send_daily_progress_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    # Database-backed reminder sweep (see notifications/reminder_processor.py)
    # -- same function core/views.py's run-scheduled-tasks endpoint calls
    # directly in production via the dedicated 5-minute 'reminders' job
    # group (see .github/workflows/scheduled-tasks.yml); this Beat entry is
    # just local dev's way of invoking the identical code on the same
    # cadence, since local dev already runs a real worker/Beat.
    "process-due-reminders": {
        "task": "notifications.tasks.process_due_reminders_task",
        "schedule": crontab(minute="*/5"),
    },
    # Admin Copilot: proactive system health sweep -- every 15 minutes
    # rather than a fixed daily hour, since infra issues need catching
    # sooner than once a day. See copilot/tasks.py.
    "copilot-system-health-check": {
        "task": "copilot.tasks.run_system_health_check",
        "schedule": crontab(minute="*/15"),
    },
    # Time-sensitive: overdue/missed reminders should be caught soon after
    # they happen, and approved actions should never sit unexecuted long.
    "copilot-reminder-check": {
        "task": "copilot.tasks.run_reminder_check",
        "schedule": crontab(minute="*/15"),
    },
    "copilot-action-agent-sweep": {
        "task": "copilot.tasks.run_action_agent_sweep",
        "schedule": crontab(minute="*/15"),
    },
    # Everything else is a daily-cadence health/insight check -- staggered
    # a few minutes apart so they don't all hit the database at once.
    "copilot-analytics-check": {
        "task": "copilot.tasks.run_analytics_check",
        "schedule": crontab(hour=8, minute=0),
    },
    "copilot-user-monitoring-check": {
        "task": "copilot.tasks.run_user_monitoring_check",
        "schedule": crontab(hour=8, minute=5),
    },
    "copilot-task-intelligence-check": {
        "task": "copilot.tasks.run_task_intelligence_check",
        "schedule": crontab(hour=8, minute=10),
    },
    "copilot-database-intelligence-check": {
        "task": "copilot.tasks.run_database_intelligence_check",
        "schedule": crontab(hour=8, minute=15),
    },
    # Runs last -- summarizes whatever the checks above just raised.
    "copilot-recommendation-digest": {
        "task": "copilot.tasks.run_recommendation_digest",
        "schedule": crontab(hour=8, minute=30),
    },
}