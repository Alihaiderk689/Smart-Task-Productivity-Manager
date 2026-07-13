from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tasks.models import Task
from tasks.serializers import TaskSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):

    user = request.user
    tasks = Task.objects.filter(user=user)

    data = {
        "total_tasks": tasks.count(),
        "pending_tasks": tasks.filter(status="Pending").count(),
        "in_progress_tasks": tasks.filter(status="In Progress").count(),
        "completed_tasks": tasks.filter(status="Completed").count(),
        "missed_tasks": tasks.filter(status="Missed").count(),
    }

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