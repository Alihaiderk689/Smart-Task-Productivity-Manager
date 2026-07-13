from django.urls import path

from .views import (TaskDetailView,
TaskListCreateView,
start_task,
pause_task,
resume_task,
stop_task,
complete_task,
reschedule_task,

)

urlpatterns = [
    path("", TaskListCreateView.as_view(), name="task-list-create"),
    path("<int:pk>/", TaskDetailView.as_view(), name="task-detail"),
    path("<int:pk>/start/", start_task, name="start-task"),
    path("<int:pk>/pause/", pause_task, name="pause-task"),
    path("<int:pk>/resume/", resume_task, name="resume-task"),
    path("<int:pk>/stop/", stop_task, name="stop-task"),
    path("<int:pk>/complete/", complete_task, name="complete-task"),
    path("<int:pk>/reschedule/", reschedule_task, name="reschedule-task"),
]
