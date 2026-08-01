from django.conf import settings
from django.db import models


class AgentRun(models.Model):
    """One Observe -> Reason -> Plan -> Execute -> Verify -> Report cycle.
    The durable record of "what did the AI do and why" -- see copilot/agents/base.py
    for the code that populates one of these."""

    TRIGGER_CHOICES = [
        ("manual", "Manual"),        # an admin clicked "run now"
        ("scheduled", "Scheduled"),  # Celery Beat
        ("chat", "Chat"),            # a natural-language command (future agents)
    ]
    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    agent_name = models.CharField(max_length=100)
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default="manual")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")

    # Summarized, not verbatim -- these are for a human (or the next agent
    # run) to read back later, not a full transcript.
    observation_summary = models.TextField(blank=True)
    reasoning_summary = models.TextField(blank=True)
    plan = models.JSONField(default=list, blank=True)
    result_summary = models.TextField(blank=True)

    confidence = models.FloatField(null=True, blank=True)  # 0.0-1.0
    error = models.TextField(blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_runs"
    )

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.agent_name} [{self.status}] @ {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def duration_ms(self):
        if not self.finished_at:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class ToolCallLog(models.Model):
    """One tool invocation within an AgentRun."""

    agent_run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="tool_calls")
    tool_name = models.CharField(max_length=100)
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True, null=True)
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.tool_name} ({'ok' if self.success else 'failed'})"


class ConversationMessage(models.Model):
    """Chat memory -- persists across sessions per admin user (see
    copilot/memory/service.py). `session_id` groups messages into threads;
    left blank, all of one user's messages are treated as one continuous
    thread."""

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("agent", "Agent"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="copilot_messages")
    session_id = models.CharField(max_length=64, blank=True, default="default")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    related_agent_run = models.ForeignKey(
        AgentRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class Recommendation(models.Model):
    """An AI-generated recommendation or alert. Covers both read-only
    observations (e.g. a system-health alert, nothing to approve) and
    proposed actions that need explicit admin approval before anything
    executes -- `action_payload` describes the tool+args to run if
    approved; blank for observation-only recommendations."""

    CATEGORY_CHOICES = [
        ("users", "User Management"),
        ("tasks", "Task Management"),
        ("reminders", "Reminders"),
        ("system", "System Health"),
        ("database", "Database"),
    ]
    RISK_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),        # awaiting admin decision
        ("approved", "Approved"),      # approved, not yet executed
        ("rejected", "Rejected"),
        ("executed", "Executed"),
        ("failed", "Failed"),          # approved, execution attempted, failed
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    reasoning = models.TextField(blank=True)   # why
    impact = models.TextField(blank=True)
    estimated_benefit = models.TextField(blank=True)
    risk = models.CharField(max_length=10, choices=RISK_CHOICES, default="low")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    confidence = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    # Non-empty only for recommendations that DO something if approved --
    # e.g. {"tool": "archive_inactive_users", "input": {"user_ids": [1,2,3]}}.
    action_payload = models.JSONField(default=dict, blank=True)
    execution_result = models.JSONField(default=dict, blank=True, null=True)

    related_agent_run = models.ForeignKey(
        AgentRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="recommendations"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_recommendations"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.status}] {self.title}"

    @property
    def requires_approval(self):
        return bool(self.action_payload)
