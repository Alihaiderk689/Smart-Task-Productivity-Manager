import csv

from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from categories.models import Category
from core.system_checks import get_system_status
from notifications.tasks import (
    send_30_minute_reminder,
    send_5_minute_reminder,
    send_overdue_reminder,
    send_progress_reminder,
)
from tasks.models import Task

from .serializers import (
    AdminTaskSerializer,
    AdminTaskWriteSerializer,
    AdminUserDetailSerializer,
    AdminUserSerializer,
)

ACTIVE_TASK_STATUSES_EXCLUDED_FROM_OVERDUE = ["Completed", "Stopped"]


def _overdue_queryset():
    return Task.objects.filter(end_time__lt=timezone.now()).exclude(
        status__in=ACTIVE_TASK_STATUSES_EXCLUDED_FROM_OVERDUE
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def distinct_category_names(request):
    """Every distinct category name across every user, for the admin task
    list's category filter -- not a list of individual Category rows (with
    16 users each having their own "Work"/"Study"/etc, that would be a
    dropdown of a hundred-plus near-duplicate entries)."""
    names = Category.objects.order_by("name").values_list("name", flat=True).distinct()
    return Response(list(names))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_overview(request):
    now = timezone.now()
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    seven_days_ago = now - timezone.timedelta(days=7)
    fourteen_days_ago = now - timezone.timedelta(days=14)

    tasks_by_status = dict(
        Task.objects.values_list("status").annotate(count=Count("id")).order_by()
    )

    return Response({
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": total_users - active_users,
        "new_users_last_7_days": User.objects.filter(date_joined__gte=seven_days_ago).count(),
        "new_users_previous_7_days": User.objects.filter(
            date_joined__gte=fourteen_days_ago, date_joined__lt=seven_days_ago
        ).count(),
        "total_tasks": Task.objects.count(),
        "total_categories": Category.objects.count(),
        "overdue_tasks": _overdue_queryset().count(),
        "tasks_by_status": tasks_by_status,
        "tasks_completed_last_7_days": Task.objects.filter(
            status="Completed", completed_at__gte=seven_days_ago
        ).count(),
        "tasks_completed_previous_7_days": Task.objects.filter(
            status="Completed", completed_at__gte=fourteen_days_ago, completed_at__lt=seven_days_ago
        ).count(),
    })


class AdminUserListView(ListAPIView):
    """All users in the system, with a task count -- staff only. Supports
    ?search=<email or name> and ?ordering=<field> (see filter_backends)."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["email", "first_name"]
    ordering_fields = ["date_joined", "email", "task_count", "last_login"]
    ordering = ["-date_joined"]

    def get_queryset(self):
        return User.objects.annotate(task_count=Count("tasks"))


class AdminUserDetailView(RetrieveAPIView):
    """A single user's profile detail -- staff only."""
    serializer_class = AdminUserDetailSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return User.objects.annotate(task_count=Count("tasks"))


class AdminUserTasksListView(ListAPIView):
    """A single user's tasks -- staff only."""
    serializer_class = AdminTaskSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        get_object_or_404(User, pk=self.kwargs["user_id"])
        return Task.objects.filter(user_id=self.kwargs["user_id"]).order_by("-created_at")


@api_view(["POST"])
@permission_classes([IsAdminUser])
def deactivate_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)

    if target.id == request.user.id:
        return Response(
            {"error": "You cannot deactivate your own account."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if target.is_superuser:
        return Response(
            {"error": "Superuser accounts cannot be deactivated here."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target.is_active = False
    target.save(update_fields=["is_active"])
    return Response({"message": "User deactivated.", "is_active": target.is_active})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def activate_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    target.is_active = True
    target.save(update_fields=["is_active"])
    return Response({"message": "User activated.", "is_active": target.is_active})


@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def delete_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)

    if target.id == request.user.id:
        return Response(
            {"error": "You cannot delete your own account."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if target.is_superuser:
        return Response(
            {"error": "Superuser accounts cannot be deleted here."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


class AdminTaskListView(ListAPIView):
    """Every task across every user -- staff only. Supports ?search=,
    ?status=, ?category=<id>, ?user=<id>, ?overdue=true, and ?ordering=."""
    serializer_class = AdminTaskSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "user__email"]
    ordering_fields = ["created_at", "start_time", "end_time", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Task.objects.select_related("category", "user")

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        category_param = self.request.query_params.get("category")
        if category_param:
            qs = qs.filter(category_id=category_param)

        # By id (above) for precise/programmatic use, or by name (below) for
        # the admin UI -- categories aren't global, every user has their own
        # "Work"/"Study"/etc, so filtering 16 users' worth of tasks by one
        # specific category id isn't very useful; filtering by name across
        # everyone's same-named category is what an admin actually wants.
        category_name_param = self.request.query_params.get("category_name")
        if category_name_param:
            qs = qs.filter(category__name__iexact=category_name_param)

        user_param = self.request.query_params.get("user")
        if user_param:
            qs = qs.filter(user_id=user_param)

        if self.request.query_params.get("overdue") == "true":
            qs = qs.filter(end_time__lt=timezone.now()).exclude(
                status__in=ACTIVE_TASK_STATUSES_EXCLUDED_FROM_OVERDUE
            )

        return qs


class AdminTaskDetailView(RetrieveUpdateDestroyAPIView):
    """View, edit, or delete any user's task -- staff only."""
    queryset = Task.objects.select_related("category", "user")
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return AdminTaskWriteSerializer
        return AdminTaskSerializer


REMINDER_TRIGGERS = {
    "30min": (send_30_minute_reminder, "reminder_30_sent"),
    "5min": (send_5_minute_reminder, "reminder_5_sent"),
    "progress": (send_progress_reminder, "reminder_progress_sent"),
    "overdue": (send_overdue_reminder, "reminder_overdue_sent"),
}


@api_view(["POST"])
@permission_classes([IsAdminUser])
def trigger_reminder(request, task_id):
    """Manually runs one of the real reminder functions right now, instead
    of waiting for its scheduled eta. Honors the exact same guards the
    automatic scheduler does (task status, already-sent) -- this can't be
    used to force a misleading email, only to run the real check early."""
    task = get_object_or_404(Task, pk=task_id)
    reminder_type = request.data.get("type")
    trigger = REMINDER_TRIGGERS.get(reminder_type)

    if not trigger:
        return Response(
            {"error": f"type must be one of {', '.join(REMINDER_TRIGGERS)}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    func, sent_field = trigger
    was_sent_before = getattr(task, sent_field)

    func(task.id, task.reminder_version)

    task.refresh_from_db()
    now_sent = getattr(task, sent_field)

    if now_sent and not was_sent_before:
        return Response({"message": "Reminder sent.", "sent": True})
    if was_sent_before:
        return Response({"message": "This reminder was already sent for this task.", "sent": False})
    return Response({
        "message": "Reminder was not sent -- this task's status doesn't currently qualify for it.",
        "sent": False,
    })


@api_view(["GET"])
@permission_classes([IsAdminUser])
def export_users_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="users.csv"'

    writer = csv.writer(response)
    writer.writerow(["ID", "Name", "Email", "Active", "Staff", "Joined", "Last Login", "Task Count"])

    users = User.objects.annotate(task_count=Count("tasks")).order_by("-date_joined")
    for u in users:
        writer.writerow([u.id, u.first_name, u.email, u.is_active, u.is_staff, u.date_joined, u.last_login or "", u.task_count])

    return response


@api_view(["GET"])
@permission_classes([IsAdminUser])
def export_tasks_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="tasks.csv"'

    writer = csv.writer(response)
    writer.writerow(["ID", "Title", "Status", "Priority", "Category", "Owner Email", "Start", "End", "Created"])

    tasks = Task.objects.select_related("category", "user").order_by("-created_at")
    for t in tasks:
        writer.writerow([
            t.id, t.title, t.status, t.priority,
            t.category.name if t.category_id else "",
            t.user.email, t.start_time, t.end_time, t.created_at,
        ])

    return response


@api_view(["GET"])
@permission_classes([IsAdminUser])
def system_status(request):
    return Response(get_system_status())
