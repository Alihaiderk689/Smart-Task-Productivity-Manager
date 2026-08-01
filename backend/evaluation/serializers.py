from rest_framework import serializers

from .models import EvalCaseResult, EvaluationRun


class EvalCaseResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalCaseResult
        fields = [
            "id", "scenario_id", "scenario_name", "category", "trigger_description",
            "expected", "actual", "passed", "failure_reason", "response_time_ms",
            "tool_selection_correct", "planning_correct", "permission_correct",
            "hallucination_detected", "error_recovered", "related_agent_run", "created_at",
        ]
        read_only_fields = fields


class EvaluationRunListSerializer(serializers.ModelSerializer):
    """Lightweight -- no nested case results, for the run history list."""
    duration_ms = serializers.ReadOnlyField()
    triggered_by_email = serializers.CharField(source="triggered_by.email", read_only=True, default=None)

    class Meta:
        model = EvaluationRun
        fields = [
            "id", "status", "triggered_by_email", "total_cases", "passed_cases", "failed_cases",
            "metrics", "started_at", "finished_at", "duration_ms",
        ]


class EvaluationRunDetailSerializer(serializers.ModelSerializer):
    duration_ms = serializers.ReadOnlyField()
    triggered_by_email = serializers.CharField(source="triggered_by.email", read_only=True, default=None)
    case_results = EvalCaseResultSerializer(many=True, read_only=True)

    class Meta:
        model = EvaluationRun
        fields = [
            "id", "status", "triggered_by_email", "total_cases", "passed_cases", "failed_cases",
            "metrics", "error", "started_at", "finished_at", "duration_ms", "case_results",
        ]
