from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from calendar import monthrange

from tasks.models import Task


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def productivity_summary(request):
    tasks = Task.objects.filter(user=request.user)

    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status="Completed").count()
    pending_tasks = tasks.filter(status="Pending").count()
    in_progress_tasks = tasks.filter(status="In Progress").count()
    missed_tasks = tasks.filter(status="Missed").count()

    if total_tasks == 0:
        productivity_score = 0
    else:
        productivity_score = round((completed_tasks / total_tasks) * 100, 2)

    data = {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "missed_tasks": missed_tasks,
        "productivity_score": productivity_score,
    }

    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def weekly_report(request):
    today = timezone.localdate()

    start_of_week = today - timedelta(days=today.weekday())

    report = []

    for i in range(7):
        day = start_of_week + timedelta(days=i)

        completed = Task.objects.filter(
            user=request.user,
            status="Completed",
            completed_at__date=day
        ).count()

        report.append({
            "date": day.strftime("%Y-%m-%d"),
            "day": day.strftime("%A"),
            "completed_tasks": completed
        })

    return Response(report)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_report(request):
    today = timezone.localdate()

    first_day = today.replace(day=1)
    last_day = today.replace(day=monthrange(today.year, today.month)[1])

    report = []

    week_number = 1
    current_start = first_day

    while current_start <= last_day:
        current_end = min(current_start + timedelta(days=6), last_day)

        completed = Task.objects.filter(
            user=request.user,
            status="Completed",
            completed_at__date__gte=current_start,
            completed_at__date__lte=current_end,
        ).count()

        report.append({
            "week": f"Week {week_number}",
            "start_date": current_start,
            "end_date": current_end,
            "completed_tasks": completed,
        })

        current_start = current_end + timedelta(days=1)
        week_number += 1

    return Response(report)