from django.urls import path
from .views import (
    productivity_summary,
    weekly_report,
    monthly_report,
)

urlpatterns = [
    path("productivity/", productivity_summary, name="productivity-summary"),
    path("weekly/", weekly_report, name="weekly-report"),
    path("monthly/", monthly_report, name="monthly-report"),
]