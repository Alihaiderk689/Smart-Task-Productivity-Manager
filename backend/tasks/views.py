import uuid
from datetime import timedelta

from rest_framework import generics
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import RetrieveUpdateDestroyAPIView

from notifications.reminder_processor import cancel_pending_reminders
from notifications.services import NotificationService

from .models import Task
from .serializers import TaskSerializer

REPEAT_MIN_DAYS = 2
REPEAT_MAX_DAYS = 30


class TaskListCreateView(generics.ListCreateAPIView):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        task = serializer.save(user=self.request.user)
        NotificationService.schedule_reminders(task)


class TaskDetailView(RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        original_start = serializer.instance.start_time
        original_end = serializer.instance.end_time
        task = serializer.save()

        if task.start_time != original_start or task.end_time != original_end:
            # A plain PATCH/PUT changing the schedule previously left
            # reminders scheduled against the old time entirely untouched
            # (a latent gap found while building the database-backed
            # reminder system) -- mirrors reschedule_task's own
            # reminder-invalidation below, without touching this
            # endpoint's other fields (status, started_at/completed_at)
            # the way the dedicated reschedule action deliberately does; a
            # generic edit shouldn't restart the task's lifecycle, only
            # its reminders.
            task.reminder_30_sent = False
            task.reminder_5_sent = False
            task.reminder_progress_sent = False
            task.reminder_overdue_sent = False
            task.last_daily_reminder_date = None
            task.reminder_version += 1
            task.save(update_fields=[
                "reminder_30_sent", "reminder_5_sent", "reminder_progress_sent",
                "reminder_overdue_sent", "last_daily_reminder_date", "reminder_version",
            ])
            NotificationService.schedule_reminders(task)


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

    if parsed_start_time <= timezone.now():
        return Response(
            {"error": "Start time cannot be in the past."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if parsed_end_time <= parsed_start_time:
        return Response(
            {"error": "End time must be after the start time."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    task.start_time = parsed_start_time
    task.end_time = parsed_end_time

    task.status = "Pending"
    task.started_at = None
    task.completed_at = None

    task.reminder_30_sent = False
    task.reminder_5_sent = False
    task.reminder_progress_sent = False
    task.reminder_overdue_sent = False
    task.last_daily_reminder_date = None

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
    """Ends a task by marking it Completed. "Stop" and "Complete" used to be
    separate actions (with separate statuses, Stopped vs Completed), but
    they meant the same thing to users -- this is now the only way to end
    an active task, so it does what /complete/ used to do."""
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
    cancel_pending_reminders(task)

    return Response({
        "message": "Task completed successfully.",
        "status": task.status,
        "completed_at": task.completed_at,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_repeating_tasks(request):
    """Creates the same task on each of N consecutive days (same time of
    day, same duration) in a single request -- e.g. "Workout every day at
    7pm for the next 7 days". Every occurrence is validated with the same
    TaskSerializer rules as a normal single create (word limits, the
    gibberish check, category ownership, ...) before any of them are
    saved, so a bad occurrence (e.g. day 5 landing on an invalid date)
    fails the whole batch instead of leaving a partial run behind. Each
    saved occurrence is a completely independent Task row with its own
    reminders, exactly as if it had been created one at a time through the
    regular endpoint -- see TaskListCreateView.perform_create."""
    try:
        repeat_days = int(request.data.get("repeat_days"))
    except (TypeError, ValueError):
        return Response({"repeat_days": ["repeat_days must be a whole number."]}, status=status.HTTP_400_BAD_REQUEST)

    if not (REPEAT_MIN_DAYS <= repeat_days <= REPEAT_MAX_DAYS):
        return Response(
            {"repeat_days": [f"repeat_days must be between {REPEAT_MIN_DAYS} and {REPEAT_MAX_DAYS}."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    base_start = parse_datetime(request.data.get("start_time") or "")
    base_end = parse_datetime(request.data.get("end_time") or "")
    if not base_start or not base_end:
        return Response(
            {"error": "Invalid datetime format for start_time or end_time."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if timezone.is_naive(base_start):
        base_start = timezone.make_aware(base_start, timezone.get_current_timezone())
    if timezone.is_naive(base_end):
        base_end = timezone.make_aware(base_end, timezone.get_current_timezone())

    base_fields = {
        "title": request.data.get("title"),
        "description": request.data.get("description", ""),
        "category": request.data.get("category"),
        "priority": request.data.get("priority"),
    }

    occurrence_serializers = []
    for day in range(repeat_days):
        occurrence = {
            **base_fields,
            "start_time": (base_start + timedelta(days=day)).isoformat(),
            "end_time": (base_end + timedelta(days=day)).isoformat(),
        }
        serializer = TaskSerializer(data=occurrence, context={"request": request})
        if not serializer.is_valid():
            return Response({"day": day, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        occurrence_serializers.append(serializer)

    # Groups every occurrence of this batch together (see the Task model's
    # repeat_group_id docstring) so the frontend can show them as one
    # "N-day series" card instead of N separate ones.
    group_id = uuid.uuid4()

    created_tasks = []
    with transaction.atomic():
        for index, serializer in enumerate(occurrence_serializers, start=1):
            task = serializer.save(
                user=request.user,
                repeat_group_id=group_id,
                repeat_index=index,
                repeat_total=repeat_days,
            )
            NotificationService.schedule_reminders(task)
            created_tasks.append(task)

    return Response({"created": TaskSerializer(created_tasks, many=True).data}, status=status.HTTP_201_CREATED)