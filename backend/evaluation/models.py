from django.conf import settings
from django.db import models


class EvaluationRun(models.Model):
    """One full pass through the evaluation suite (see evaluation/scenarios.py
    for the scenario list and evaluation/runner.py for the engine that
    executes them against the real running app). The aggregate metrics are
    computed once at the end from this run's EvalCaseResult rows -- see
    evaluation/metrics.py."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),  # the harness itself blew up, not an individual case
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="evaluation_runs"
    )

    total_cases = models.PositiveIntegerField(default=0)
    passed_cases = models.PositiveIntegerField(default=0)
    failed_cases = models.PositiveIntegerField(default=0)

    # task_success_rate, tool_selection_accuracy, planning_accuracy,
    # permission_accuracy, error_recovery_rate, hallucination_rate,
    # avg_response_time_ms, workflow_completion_rate -- see metrics.py for
    # exactly how each is computed and what "not applicable" (None) means.
    metrics = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Eval run #{self.id} [{self.status}] {self.passed_cases}/{self.total_cases} passed"

    @property
    def duration_ms(self):
        if not self.finished_at:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class EvalCaseResult(models.Model):
    """One scenario's outcome within an EvaluationRun -- the "detailed log"
    the admin dashboard drills into. `expected` and `actual` are free-form
    JSON snapshots (shape varies by category) rather than fixed columns,
    since a chat scenario's actual behavior looks very different from an
    agent-run or failure-injection scenario's."""

    CATEGORY_CHOICES = [
        ("task_visibility", "Task Visibility"),
        ("task_maintenance", "Task Maintenance"),
        ("user_management", "User Management"),
        ("reminders", "Reminders"),
        ("analytics", "Analytics"),
        ("system_maintenance", "System Maintenance"),
        ("permission", "Permission Boundary"),
        ("failure_injection", "Failure Injection"),
        ("workflow", "End-to-End Workflow"),
    ]

    run = models.ForeignKey(EvaluationRun, on_delete=models.CASCADE, related_name="case_results")

    scenario_id = models.CharField(max_length=100)
    scenario_name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    trigger_description = models.TextField(blank=True)

    expected = models.JSONField(default=dict, blank=True)
    actual = models.JSONField(default=dict, blank=True)

    passed = models.BooleanField(default=False)
    failure_reason = models.TextField(blank=True)
    response_time_ms = models.PositiveIntegerField(default=0)

    # Each is None when the dimension doesn't apply to this scenario (e.g.
    # a permission-boundary case has no "hallucination" to check) -- see
    # metrics.py, which only averages over the non-None rows per dimension.
    tool_selection_correct = models.BooleanField(null=True, blank=True)
    planning_correct = models.BooleanField(null=True, blank=True)
    permission_correct = models.BooleanField(null=True, blank=True)
    hallucination_detected = models.BooleanField(null=True, blank=True)
    error_recovered = models.BooleanField(null=True, blank=True)

    related_agent_run = models.ForeignKey(
        "copilot.AgentRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="eval_case_results"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.scenario_name}"
