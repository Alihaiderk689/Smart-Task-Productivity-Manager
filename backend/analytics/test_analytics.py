import pytest
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

@pytest.mark.django_db
def test_productivity_summary_empty(auth_client):
    response = auth_client.get("/api/analytics/productivity/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["productivity_score"] == 0

@pytest.mark.django_db
def test_productivity_summary_with_tasks(auth_client, task_factory):
    task_factory(status="Completed")
    task_factory(status="Completed")
    task_factory(status="Pending")
    task_factory(status="Missed")
    
    response = auth_client.get("/api/analytics/productivity/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_tasks"] == 4
    assert response.data["completed_tasks"] == 2
    assert response.data["productivity_score"] == 50.0

@pytest.mark.django_db
def test_weekly_report(auth_client, task_factory):
    today = timezone.localdate()
    # Create tasks completed today, yesterday, and last week (outside current week)
    completed_time_today = timezone.now()
    completed_time_yesterday = timezone.now() - timedelta(days=1)
    completed_time_old = timezone.now() - timedelta(days=10)
    
    task_factory(status="Completed", completed_at=completed_time_today)
    task_factory(status="Completed", completed_at=completed_time_yesterday)
    task_factory(status="Completed", completed_at=completed_time_old)
    
    response = auth_client.get("/api/analytics/weekly/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 7
    
    total_completed_in_week = sum(day["completed_tasks"] for day in response.data)
    # Today and yesterday should be in the report if they fall within the current week
    # We can verify that at least today's task is counted
    today_str = today.strftime("%Y-%m-%d")
    for day in response.data:
        if day["date"] == today_str:
            assert day["completed_tasks"] == 1

@pytest.mark.django_db
def test_monthly_report(auth_client, task_factory):
    response = auth_client.get("/api/analytics/monthly/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) > 0
    assert "week" in response.data[0]
    assert "completed_tasks" in response.data[0]
