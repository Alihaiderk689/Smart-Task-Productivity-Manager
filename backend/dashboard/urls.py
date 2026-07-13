from django.urls import path
from .views import (
    dashboard_summary,
    today_tasks,
    upcoming_tasks,
    high_priority_tasks,
    missed_tasks,
)

urlpatterns = [
    path("summary/", dashboard_summary, name="dashboard-summary"),
    path("today/", today_tasks, name="today-tasks"),
    path("high-priority/", high_priority_tasks, name="high-priority-tasks"),
    path("upcoming/", upcoming_tasks, name="upcoming-tasks"),
    path("missed/", missed_tasks, name="missed-tasks"),
]

