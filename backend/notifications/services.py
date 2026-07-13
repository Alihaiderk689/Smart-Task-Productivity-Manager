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

        print(f"Scheduling reminders for task {task.id}")
        version = task.reminder_version

        # 30-minute reminder
        reminder_30 = task.start_time - timedelta(minutes=30)
        print("Scheduling reminder for:", reminder_30)
        print("Current time:", timezone.now())
        print("Reminder time:", reminder_30)

        if reminder_30 > timezone.now():
            send_30_minute_reminder.apply_async(
                args=[task.id, version],
                eta=reminder_30,
            )
        else:
            print("Reminder time already passed")

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