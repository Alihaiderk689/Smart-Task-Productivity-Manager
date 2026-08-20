import logging
import time

from django.core.management.base import BaseCommand

from notifications.reminder_processor import process_due_reminders
from notifications.tasks import send_daily_progress_reminders

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Local-dev-only stand-in for the GitHub Actions scheduled-tasks "
        "workflow that drives reminders in production. Repeatedly calls "
        "process_due_reminders() (and, once an hour, "
        "send_daily_progress_reminders()) so reminders created while "
        "developing actually fire without a manual shell command each "
        "time. Never run this in production -- the GitHub Actions cron "
        "already covers that, and this has no locking against a second "
        "instance."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Seconds between sweeps (default: 60).",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        self.stdout.write(self.style.SUCCESS(f"Reminder sweep loop started (every {interval}s). Ctrl+C to stop."))

        last_daily_run_hour = None

        try:
            while True:
                try:
                    result = process_due_reminders()
                    if result["claimed"]:
                        self.stdout.write(f"Swept {result['claimed']} due reminder(s).")
                except Exception:
                    logger.exception("Reminder sweep iteration failed")

                # send_daily_progress_reminders is itself idempotent per day
                # (checks last_daily_reminder_date) -- only bothering to
                # call it once an hour, not every minute, since multi-day
                # task check-ins don't need minute-level timeliness.
                from django.utils import timezone

                current_hour = timezone.now().hour
                if current_hour != last_daily_run_hour:
                    last_daily_run_hour = current_hour
                    try:
                        send_daily_progress_reminders()
                    except Exception:
                        logger.exception("Daily progress reminder sweep failed")

                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Reminder sweep loop stopped."))
