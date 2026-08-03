from django.utils import timezone
from rest_framework import serializers

from categories.models import Category

from .models import Task
from .validators import looks_like_gibberish

GIBBERISH_MESSAGE = "This doesn't look like real text -- please rewrite it in plain words."

TITLE_MAX_WORDS = 20
DESCRIPTION_MAX_WORDS = 200


def _word_count(value):
    return len(value.split())


class TaskSerializer(serializers.ModelSerializer):
    # Has a model-level default ("Medium"), which would otherwise make DRF
    # treat it as optional -- redeclared so the user always has to choose
    # one explicitly instead of silently getting the default.
    priority = serializers.ChoiceField(
        choices=Task.PRIORITY_CHOICES,
        error_messages={"required": "Please select a priority.", "invalid_choice": "Please select a valid priority."},
    )
    # Redeclared (instead of the ModelSerializer-inferred field) so the
    # queryset can be scoped to the current user in __init__ below -- a task
    # must not be assignable to another user's category.
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.none(),
        error_messages={
            "required": "Please select a category.",
            "does_not_exist": "Please select a valid category.",
        },
    )

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
            "reminder_overdue_sent",
            "reminder_version",
            "rescheduled_count",
            "last_daily_reminder_date",
            # Only ever set internally by create_repeating_tasks (see
            # tasks/views.py) -- never accepted as client input, on a plain
            # create or update.
            "repeat_group_id",
            "repeat_index",
            "repeat_total",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            self.fields["category"].queryset = Category.objects.filter(user=request.user)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Task name is required.")
        if _word_count(value) > TITLE_MAX_WORDS:
            raise serializers.ValidationError(f"Task name cannot exceed {TITLE_MAX_WORDS} words.")
        if looks_like_gibberish(value):
            raise serializers.ValidationError(GIBBERISH_MESSAGE)
        return value

    def validate_description(self, value):
        value = (value or "").strip()
        if value and _word_count(value) > DESCRIPTION_MAX_WORDS:
            raise serializers.ValidationError(f"Description cannot exceed {DESCRIPTION_MAX_WORDS} words.")
        if value and looks_like_gibberish(value):
            raise serializers.ValidationError(GIBBERISH_MESSAGE)
        return value

    def validate_start_time(self, value):
        # Editing lets an unchanged start_time through even if it's since
        # slipped into the past (e.g. tweaking the description on a task
        # that's already started) -- the frontend always resends the whole
        # form on save, not just the fields that changed, so this can't be
        # narrowed to "only check on create" without breaking normal edits.
        if self.instance is not None and value == self.instance.start_time:
            return value
        if value <= timezone.now():
            raise serializers.ValidationError("Start time cannot be in the past.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": "End time must be after the start time."})
        return attrs
