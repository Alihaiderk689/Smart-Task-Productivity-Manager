from django.db import models            #mports Django's tools for creating database tables.
from django.contrib.auth.models import User


class Task(models.Model):

    PRIORITY_CHOICES = [            #choices for the priority field, which is a dropdown in the admin panel.
        ("Low", "Low"),
        ("Medium", "Medium"),
        ("High", "High"),
    ]

    STATUS_CHOICES = [

    ("Pending", "Pending"),
    ("In Progress", "In Progress"),
    ("Paused", "Paused"),
    ("Completed", "Completed"),
    ("Stopped", "Stopped"),
    ("Missed", "Missed"),

]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tasks"
    )

    category = models.ForeignKey(           #connects the task to a categoory.  
        "categories.Category",
        on_delete=models.CASCADE,
        related_name="tasks"
    )

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,       
        default="Medium"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Pending"
    )

    # Planned schedule
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    # Actual timings
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Reminder tracking
    reminder_30_sent = models.BooleanField(default=False)
    reminder_5_sent = models.BooleanField(default=False)
    reminder_progress_sent = models.BooleanField(default=False)
    reminder_overdue_sent=models.BooleanField(default=False)

    # Rescheduling
    #we use reminder_version in case if any user rescheduled the task, then the old reminder should be cancelled and new reminder should be sent. 

    reminder_version = models.PositiveIntegerField(default=1)
    rescheduled_count = models.PositiveIntegerField(default=0)

    # Multi-day tasks (duration > 1 day) get a daily "still ongoing" email via
    # a Celery Beat sweep (notifications.tasks.send_daily_progress_reminders)
    # instead of the one-shot apply_async reminders above. This tracks the
    # last calendar day it was sent so the sweep doesn't double-send.
    last_daily_reminder_date = models.DateField(null=True, blank=True)

    # Repeat series (see tasks/views.py::create_repeating_tasks) -- each day
    # of a repeated task ("Workout, daily for 7 days") is still its own real
    # Task row with its own status/reminders (a single row can't be "done
    # Monday, still pending Tuesday"), but these three fields let the
    # frontend group same-series rows back into one card instead of N.
    # Null for every task created the normal, non-repeating way.
    repeat_group_id = models.UUIDField(null=True, blank=True, db_index=True)
    repeat_index = models.PositiveIntegerField(null=True, blank=True)
    repeat_total = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

def __str__(self):
    return self.title