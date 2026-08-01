from rest_framework import serializers

from .models import AgentRun, ConversationMessage, Recommendation, ToolCallLog


class ToolCallLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolCallLog
        fields = ["id", "tool_name", "input_data", "output_data", "success", "error", "duration_ms", "created_at"]


class AgentRunListSerializer(serializers.ModelSerializer):
    """Lighter-weight than AgentRunSerializer -- no nested tool_calls, for
    list views where that would mean N+1-ish payload bloat."""
    duration_ms = serializers.ReadOnlyField()

    class Meta:
        model = AgentRun
        fields = [
            "id", "agent_name", "trigger", "status", "result_summary",
            "confidence", "started_at", "finished_at", "duration_ms",
        ]


class AgentRunSerializer(serializers.ModelSerializer):
    tool_calls = ToolCallLogSerializer(many=True, read_only=True)
    duration_ms = serializers.ReadOnlyField()

    class Meta:
        model = AgentRun
        fields = [
            "id", "agent_name", "trigger", "status",
            "observation_summary", "reasoning_summary", "plan", "result_summary",
            "confidence", "error", "started_at", "finished_at", "duration_ms", "tool_calls",
        ]


class RecommendationSerializer(serializers.ModelSerializer):
    requires_approval = serializers.ReadOnlyField()

    class Meta:
        model = Recommendation
        fields = [
            "id", "title", "description", "reasoning", "impact", "estimated_benefit",
            "risk", "category", "confidence", "status", "requires_approval",
            "related_agent_run", "created_at", "resolved_at",
        ]
        read_only_fields = fields


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ["id", "role", "content", "session_id", "related_agent_run", "created_at"]
        read_only_fields = fields


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(trim_whitespace=True, max_length=2000)
    session_id = serializers.CharField(required=False, default="default", max_length=64)

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        return value
