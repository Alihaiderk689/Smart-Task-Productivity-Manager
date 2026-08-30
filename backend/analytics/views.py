from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from calendar import monthrange

from tasks.models import Task


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def productivity_summary(request):
    # One aggregate query instead of 5 sequential .count() calls -- same
    # pattern already used correctly in adminpanel/views.py::admin_overview.
    # See SCALABILITY_AUDIT.md's H2.
    counts = Task.objects.filter(user=request.user).aggregate(
        total_tasks=Count("id"),
        completed_tasks=Count("id", filter=Q(status="Completed")),
        pending_tasks=Count("id", filter=Q(status="Pending")),
        in_progress_tasks=Count("id", filter=Q(status="In Progress")),
        missed_tasks=Count("id", filter=Q(status="Missed")),
    )

    if counts["total_tasks"] == 0:
        productivity_score = 0
    else:
        productivity_score = round((counts["completed_tasks"] / counts["total_tasks"]) * 100, 2)

    data = {**counts, "productivity_score": productivity_score}

    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def weekly_report(request):
    today = timezone.localdate()

    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # One grouped query instead of one .count() per day (7 queries) -- see
    # SCALABILITY_AUDIT.md's H2. TruncDate honors settings.TIME_ZONE the
    # same way the previous per-day completed_at__date=day lookup did, so
    # the day buckets line up identically.
    rows = (
        Task.objects.filter(
            user=request.user,
            status="Completed",
            completed_at__date__gte=start_of_week,
            completed_at__date__lte=end_of_week,
        )
        .annotate(day=TruncDate("completed_at"))
        .values("day")
        .annotate(completed_tasks=Count("id"))
    )
    counts_by_day = {row["day"]: row["completed_tasks"] for row in rows}

    report = []
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        report.append({
            "date": day.strftime("%Y-%m-%d"),
            "day": day.strftime("%A"),
            "completed_tasks": counts_by_day.get(day, 0),
        })

    return Response(report)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_report(request):
    today = timezone.localdate()

    first_day = today.replace(day=1)
    last_day = today.replace(day=monthrange(today.year, today.month)[1])

    # One grouped query for the whole month instead of one .count() per
    # week (~4-5 queries) -- see SCALABILITY_AUDIT.md's H2. Same
    # TruncDate/timezone reasoning as weekly_report above.
    rows = (
        Task.objects.filter(
            user=request.user,
            status="Completed",
            completed_at__date__gte=first_day,
            completed_at__date__lte=last_day,
        )
        .annotate(day=TruncDate("completed_at"))
        .values("day")
        .annotate(completed_tasks=Count("id"))
    )
    counts_by_day = {row["day"]: row["completed_tasks"] for row in rows}

    report = []

    week_number = 1
    current_start = first_day

    while current_start <= last_day:
        current_end = min(current_start + timedelta(days=6), last_day)

        completed = sum(
            counts_by_day.get(current_start + timedelta(days=offset), 0)
            for offset in range((current_end - current_start).days + 1)
        )

        report.append({
            "week": f"Week {week_number}",
            "start_date": current_start,
            "end_date": current_end,
            "completed_tasks": completed,
        })

        current_start = current_end + timedelta(days=1)
        week_number += 1

    return Response(report)