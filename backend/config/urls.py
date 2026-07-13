from django.contrib import admin        #django built in admin panel.
from django.urls import path, include          #django built in urls module to include urls from other apps.

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
    path("admin/", admin.site.urls),
    path("api/tasks/", include("tasks.urls")),
    path("api/", include("users.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/categories/", include("categories.urls")),
    path("upcoming/", upcoming_tasks, name="upcoming-tasks"),
    path("api/analytics/", include("analytics.urls")),
    path("missed/", missed_tasks, name="missed-tasks"),
    path("high-priority/", high_priority_tasks, name="high-priority-tasks"),
]