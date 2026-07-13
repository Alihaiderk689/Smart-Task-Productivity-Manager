from rest_framework import serializers
from .models import Task


class TaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = [
            "id",
            "user",
            "status",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "reminder_30_sent",
            "reminder_5_sent",
            "reminder_progress_sent",
            "rescheduled_count",
        ]