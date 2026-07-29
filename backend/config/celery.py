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
}