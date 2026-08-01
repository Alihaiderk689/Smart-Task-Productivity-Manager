from django.contrib.auth.models import User
from rest_framework import serializers

from tasks.models import Task
from tasks.serializers import DESCRIPTION_MAX_WORDS, TITLE_MAX_WORDS
from users.models import Profile


def _word_count(value):
    return len(value.split())


class AdminUserSerializer(serializers.ModelSerializer):
    # Annotated on the queryset in views.AdminUserListView -- not a real
    # model field, so it has to be declared explicitly here.
    task_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "email",
            "is_active",
            "is_staff",
            "date_joined",
            "last_login",
            "task_count",
        ]


class AdminUserDetailSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
            "task_count",
            "avatar",
        ]

    def get_avatar(self, user):
        profile = Profile.objects.filter(user=user).first()
        if not profile or not profile.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(profile.avatar.url) if request else profile.avatar.url


class AdminTaskSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "category",
            "category_name",
            "user_id",
            "user_email",
            "start_time",
            "end_time",
            "created_at",
            "reminder_30_sent",
            "reminder_5_sent",
            "reminder_progress_sent",
            "reminder_overdue_sent",
        ]


class AdminTaskWriteSerializer(serializers.ModelSerializer):
    """Used by AdminTaskDetailView's PATCH -- an admin editing any user's
    task. Deliberately more lenient than the regular tasks.TaskSerializer:
    no "can't be in the past" check (an admin may legitimately need to
    correct/backdate a task), but keeps the data-hygiene rules (word limits,
    end-after-start, category must belong to the task's own owner -- not
    the admin)."""

    class Meta:
        model = Task
        fields = ["title", "description", "status", "priority", "category", "start_time", "end_time"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Task name is required.")
        if _word_count(value) > TITLE_MAX_WORDS:
            raise serializers.ValidationError(f"Task name cannot exceed {TITLE_MAX_WORDS} words.")
        return value

    def validate_description(self, value):
        value = (value or "").strip()
        if value and _word_count(value) > DESCRIPTION_MAX_WORDS:
            raise serializers.ValidationError(f"Description cannot exceed {DESCRIPTION_MAX_WORDS} words.")
        return value

    def validate_category(self, value):
        if self.instance is not None and value.user_id != self.instance.user_id:
            raise serializers.ValidationError("Category must belong to the task's own owner.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": "End time must be after the start time."})
        return attrs
