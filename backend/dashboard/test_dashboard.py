import pytest
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

@pytest.mark.django_db
def test_dashboard_summary(auth_client, task_factory):
    task_factory(status="Pending")
    task_factory(status="In Progress")
    task_factory(status="Completed")
    task_factory(status="Missed")
    
    response = auth_client.get("/api/dashboard/summary/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_tasks"] == 4
    assert response.data["pending_tasks"] == 1
    assert response.data["in_progress_tasks"] == 1
    assert response.data["completed_tasks"] == 1
    assert response.data["missed_tasks"] == 1

@pytest.mark.django_db
def test_today_tasks(auth_client, task_factory):
    today_start = timezone.now().replace(hour=8, minute=0, second=0)
    tomorrow_start = today_start + timedelta(days=1)
    
    task_factory(title="Today's Task", start_time=today_start)
    task_factory(title="Tomorrow's Task", start_time=tomorrow_start)
    
    response = auth_client.get("/api/dashboard/today/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["title"] == "Today's Task"

@pytest.mark.django_db
def test_upcoming_tasks(auth_client, task_factory):
    now = timezone.now()
    task_factory(title="Past Task", start_time=now - timedelta(hours=2))
    task_factory(title="Upcoming Task", start_time=now + timedelta(hours=2))
    
    response = auth_client.get("/api/dashboard/upcoming/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["title"] == "Upcoming Task"

@pytest.mark.django_db
def test_high_priority_tasks(auth_client, task_factory):
    task_factory(title="Medium Priority Task", priority="Medium")
    task_factory(title="High Priority Task", priority="High")
    
    response = auth_client.get("/api/dashboard/high-priority/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["title"] == "High Priority Task"

@pytest.mark.django_db
def test_missed_tasks(auth_client, task_factory):
    task_factory(title="Completed Task", status="Completed")
    task_factory(title="Missed Task", status="Missed")
    
    response = auth_client.get("/api/dashboard/missed/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["title"] == "Missed Task"
