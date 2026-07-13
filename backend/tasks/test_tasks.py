import pytest
from rest_framework import status
from tasks.models import Task
from django.utils import timezone
from datetime import timedelta

@pytest.mark.django_db
def test_list_tasks(auth_client, test_user, task_factory):
    task_factory(title="Task 1", user=test_user)
    task_factory(title="Task 2", user=test_user)
    
    # Other user task
    from django.contrib.auth.models import User
    other_user = User.objects.create_user(username="other@example.com", password="Password123!")
    task_factory(title="Other Task", user=other_user)
    
    response = auth_client.get("/api/tasks/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2
    titles = [t["title"] for t in response.data]
    assert "Task 1" in titles
    assert "Task 2" in titles
    assert "Other Task" not in titles

@pytest.mark.django_db
def test_create_task_success(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    now = timezone.now()
    response = auth_client.post(
        "/api/tasks/",
        {
            "title": "Build Pytest",
            "description": "Write all tests",
            "category": category.id,
            "priority": "High",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat()
        },
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert Task.objects.filter(title="Build Pytest", user=test_user).exists()

@pytest.mark.django_db
def test_start_task_flow(auth_client, task_factory):
    task = task_factory(status="Pending")
    response = auth_client.post(f"/api/tasks/{task.id}/start/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "In Progress"
    assert task.started_at is not None

@pytest.mark.django_db
def test_start_task_invalid_state(auth_client, task_factory):
    task = task_factory(status="Completed")
    response = auth_client.post(f"/api/tasks/{task.id}/start/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "Task cannot be started."

@pytest.mark.django_db
def test_complete_task_success(auth_client, task_factory):
    task = task_factory(status="In Progress")
    response = auth_client.post(f"/api/tasks/{task.id}/complete/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "Completed"
    assert task.completed_at is not None

@pytest.mark.django_db
def test_complete_task_already_completed(auth_client, task_factory):
    task = task_factory(status="Completed")
    response = auth_client.post(f"/api/tasks/{task.id}/complete/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "Task is already completed."

@pytest.mark.django_db
def test_complete_task_pending_fails(auth_client, task_factory):
    task = task_factory(status="Pending")
    response = auth_client.post(f"/api/tasks/{task.id}/complete/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "Start the task before completing it."

@pytest.mark.django_db
def test_pause_task_success(auth_client, task_factory):
    task = task_factory(status="In Progress")
    response = auth_client.post(f"/api/tasks/{task.id}/pause/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "Paused"

@pytest.mark.django_db
def test_pause_task_completed_fails(auth_client, task_factory):
    task = task_factory(status="Completed")
    response = auth_client.post(f"/api/tasks/{task.id}/pause/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Completed tasks cannot be paused." in response.data["error"]

@pytest.mark.django_db
def test_resume_task_success(auth_client, task_factory):
    task = task_factory(status="Paused")
    response = auth_client.post(f"/api/tasks/{task.id}/resume/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "In Progress"

@pytest.mark.django_db
def test_stop_task_success(auth_client, task_factory):
    task = task_factory(status="In Progress")
    response = auth_client.post(f"/api/tasks/{task.id}/stop/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "Paused"

@pytest.mark.django_db
def test_stop_task_already_paused(auth_client, task_factory):
    task = task_factory(status="Paused")
    response = auth_client.post(f"/api/tasks/{task.id}/stop/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "Paused"

@pytest.mark.django_db
def test_stop_task_rejects_completed(auth_client, task_factory):
    task = task_factory(status="Completed")
    response = auth_client.post(f"/api/tasks/{task.id}/stop/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    task.refresh_from_db()
    assert task.status == "Completed"

@pytest.mark.django_db
def test_reschedule_task_success(auth_client, task_factory):
    task = task_factory(status="Completed", rescheduled_count=1)
    new_start = timezone.now() + timedelta(days=1)
    new_end = new_start + timedelta(hours=1)
    response = auth_client.post(
        f"/api/tasks/{task.id}/reschedule/",
        {
            "start_time": new_start.isoformat(),
            "end_time": new_end.isoformat()
        },
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "Pending"
    assert task.rescheduled_count == 2
    assert task.started_at is None
    assert task.completed_at is None
    assert task.reminder_30_sent is False
