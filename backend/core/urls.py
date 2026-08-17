from django.urls import path

from . import views

urlpatterns = [
    path("run-scheduled-tasks/", views.run_scheduled_tasks, name="run-scheduled-tasks"),
    path("health/", views.health, name="health"),
]
