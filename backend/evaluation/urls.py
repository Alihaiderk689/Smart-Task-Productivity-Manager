from django.urls import path

from . import views

urlpatterns = [
    path("run/", views.trigger_evaluation, name="evaluation-run"),
    path("runs/", views.EvaluationRunListView.as_view(), name="evaluation-run-list"),
    path("runs/<int:pk>/", views.EvaluationRunDetailView.as_view(), name="evaluation-run-detail"),
    path("summary/", views.latest_summary, name="evaluation-summary"),
]
