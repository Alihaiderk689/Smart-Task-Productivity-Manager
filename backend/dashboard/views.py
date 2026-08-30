from django.db.models import Count, Q
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tasks.models import Task
from tasks.serializers import TaskSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    # One aggregate query instead of 5 sequential .count() calls -- same
    # pattern already used correctly in adminpanel/views.py::admin_overview.
    # See SCALABILITY_AUDIT.md's H2.
    data = Task.objects.filter(user=request.user).aggregate(
        total_tasks=Count("id"),
        pending_tasks=Count("id", filter=Q(status="Pending")),
        in_progress_tasks=Count("id", filter=Q(status="In Progress")),
        completed_tasks=Count("id", filter=Q(status="Completed")),
        missed_tasks=Count("id", filter=Q(status="Missed")),
    )

    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def today_tasks(request):
    today = timezone.localdate()

    tasks = Task.objects.filter(
        user=request.user,
        start_time__date=today
    ).order_by("start_time")

    serializer = TaskSerializer(tasks, many=True)

    return Response(serializer.data) 


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def upcoming_tasks(request):
    now = timezone.now()

    tasks = Task.objects.filter(
        user=request.user,
        start_time__gt=now
    ).order_by("start_time")

    serializer = TaskSerializer(tasks, many=True)

    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def high_priority_tasks(request):
    tasks = Task.objects.filter(
        user=request.user,
        priority="High"
    ).order_by("start_time")

    serializer = TaskSerializer(tasks, many=True)

    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def missed_tasks(request):
    tasks = Task.objects.filter(
        user=request.user,
        status="Missed"
    ).order_by("-end_time")

    serializer = TaskSerializer(tasks, many=True)

    return Response(serializer.data)