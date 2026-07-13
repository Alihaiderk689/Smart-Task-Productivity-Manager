from rest_framework import generics
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import RetrieveUpdateDestroyAPIView

from notifications.services import NotificationService

from .models import Task
from .serializers import TaskSerializer


class TaskListCreateView(generics.ListCreateAPIView):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def perform_create(self, serializer):

        print("perform_create called")
        task = serializer.save(user=self.request.user)
        print(f"Task created: {task.id}")
        NotificationService.schedule_reminders(task)
        print("Finished scheduling")


class TaskDetailView(RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_task(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)

    except Task.DoesNotExist:
        return Response(
            {"message": "Task not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    if task.status != "Pending":
        return Response(
            {"message": "Task cannot be started."},
            status=status.HTTP_400_BAD_REQUEST
        )

    task.status = "In Progress"
    task.started_at = timezone.now()
    task.save()
    return Response(
        {
            "message": "Task started successfully.",
            "status": task.status,
            "started_at": task.started_at,
        },
        status=status.HTTP_200_OK

    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_task(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response(
            {"error": "Task not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if task.status == "Completed":
        return Response(
            {"message": "Task is already completed."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if task.status == "Pending":
        return Response(
            {"message": "Start the task before completing it."},
            status=status.HTTP_400_BAD_REQUEST
        )

    task.status = "Completed"
    task.completed_at = timezone.now()
    task.save()

    return Response({
        "message": "Task completed successfully.",
        "status": task.status,
        "completed_at": task.completed_at,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reschedule_task(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response(
            {"error": "Task not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    start_time = request.data.get("start_time")
    end_time = request.data.get("end_time")

    if not start_time or not end_time:
        return Response(
            {"error": "start_time and end_time are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    parsed_start_time = parse_datetime(start_time)
    parsed_end_time = parse_datetime(end_time)

    if not parsed_start_time or not parsed_end_time:
        return Response(
            {"error": "Invalid datetime format for start_time or end_time."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if timezone.is_naive(parsed_start_time):
        parsed_start_time = timezone.make_aware(parsed_start_time, timezone.get_current_timezone())
    if timezone.is_naive(parsed_end_time):
        parsed_end_time = timezone.make_aware(parsed_end_time, timezone.get_current_timezone())

    task.start_time = parsed_start_time
    task.end_time = parsed_end_time

    task.status = "Pending"
    task.started_at = None
    task.completed_at = None

    task.reminder_30_sent = False
    task.reminder_5_sent = False
    task.reminder_progress_sent = False

    task.reminder_version += 1
    task.rescheduled_count += 1

    task.save()
    NotificationService.schedule_reminders(task)
    
    return Response({
        "message": "Task rescheduled successfully.",
        "rescheduled_count": task.rescheduled_count,
        "start_time": task.start_time,
        "end_time": task.end_time,
        "status": task.status,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pause_task(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response(
            {"error": "Task not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if task.status == "Completed":
        return Response(
            {"error": "Completed tasks cannot be paused."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if task.status == "Pending":
        return Response(
            {"error": "Start the task before pausing it."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if task.status == "Paused":
        return Response(
            {"message": "Task is already paused."},
            status=status.HTTP_200_OK
        )

    if task.status == "Stopped":
        return Response(
            {"error": "Stopped tasks cannot be paused."},
            status=status.HTTP_400_BAD_REQUEST
        )

    task.status = "Paused"
    task.save()

    return Response({
        "message": "Task paused successfully.",
        "status": task.status,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resume_task(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response(
            {"error": "Task not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if task.status == "Pending":
        return Response(
            {"error": "Start the task before resuming it."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if task.status == "Completed":
        return Response(
            {"error": "Completed tasks cannot be resumed."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if task.status == "Stopped":
        return Response(
            {"error": "Stopped tasks cannot be resumed."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if task.status == "In Progress":
        return Response(
            {"message": "Task is already in progress."},
            status=status.HTTP_200_OK
        )

    task.status = "In Progress"
    task.save()

    return Response({
        "message": "Task resumed successfully.",
        "status": task.status,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def stop_task(request, pk):
    try:
        task = Task.objects.get(pk=pk, user=request.user)
    except Task.DoesNotExist:
        return Response(
            {"error": "Task not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if task.status == "Completed":
        return Response(
            {"error": "Completed tasks cannot be stopped."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if task.status == "Paused":
        return Response(
            {"message": "Task is already paused."},
            status=status.HTTP_200_OK
        )

    task.status = "Paused"
    task.save()

    return Response({
        "message": "Task paused successfully.",
        "status": task.status,
    })