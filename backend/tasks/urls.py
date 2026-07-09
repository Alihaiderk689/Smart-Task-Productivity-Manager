from django.urls import path
from .views import TaskListCreateView

urlpatterns = [
    path("", TaskListCreateView.as_view(), name="task-list-create"),
]