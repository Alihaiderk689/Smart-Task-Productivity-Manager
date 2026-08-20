from django.db import models


class Reminder(models.Model):
    """A single scheduled reminder email for a task -- the persistent,
    database-backed replacement for the old apply_async(eta=...) scheduling
    (see notifications/reminder_processor.py for the processing/delivery
    side, and its module docstring for the at-least-once delivery
    guarantee this model exists to support).

    `scheduled_for` is the field the old Celery-ETA approach never
    persisted anywhere: without it, nothing but an in-memory broker message
    knew *when* a reminder was due, which is exactly why the free-tier
    production deployment (no Redis/worker) could never fire these on
    schedule. A periodic sweep only works because this timestamp is now a
    real, queryable column.
    """

    class Kind(models.TextChoices):
        THIRTY_MIN = "30min", "30 minutes before"
        FIVE_MIN = "5min", "5 minutes before"
        PROGRESS = "progress", "Progress check-in"
        OVERDUE = "overdue", "Overdue"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="reminders")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    scheduled_for = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    # Mirrors Task.reminder_version at the moment this row was created --
    # deliberately not a new concept, just reusing the field that already
    # exists for exactly this purpose (see Task.reminder_version's own
    # docstring). A reschedule bumps task.reminder_version, which makes any
    # Reminder row still carrying the old number permanently unclaimable
    # (see reminder_processor._claim_batch's generation filter) -- no
    # explicit cleanup pass is required for correctness, only for tidiness
    # (generate_reminders_for_task also proactively cancels old pending
    # rows -- see its docstring).
    generation = models.PositiveIntegerField()

    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    # Processing-lease timestamp -- lets a later sweep recognize and reclaim
    # a row whose claimer died mid-send (Render restart, killed Action)
    # without needing a distributed lock. See reminder_processor.STALE_LEASE.
    claimed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "kind", "generation"],
                name="unique_reminder_per_task_kind_generation",
            ),
        ]

    def __str__(self):
        return f"{self.kind} reminder for task {self.task_id} ({self.status})"
