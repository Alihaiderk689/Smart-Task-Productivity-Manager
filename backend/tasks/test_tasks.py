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

def _task_payload(category, **overrides):
    start = timezone.now() + timedelta(hours=1)
    payload = {
        "title": "Build Pytest",
        "description": "Write all tests",
        "category": category.id,
        "priority": "High",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=2)).isoformat(),
    }
    payload.update(overrides)
    return payload

@pytest.mark.django_db
def test_create_task_success(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(category),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert Task.objects.filter(title="Build Pytest", user=test_user).exists()

@pytest.mark.django_db
def test_create_task_rejects_title_over_20_words(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    long_title = " ".join(["word"] * 21)
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(category, title=long_title),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "title" in response.data

@pytest.mark.django_db
def test_create_task_allows_title_at_20_words(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    title = " ".join(["word"] * 20)
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(category, title=title),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED

@pytest.mark.django_db
def test_create_task_rejects_description_over_200_words(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    long_description = " ".join(["word"] * 201)
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(category, description=long_description),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "description" in response.data

@pytest.mark.django_db
def test_create_task_allows_description_at_200_words(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    description = " ".join(["word"] * 200)
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(category, description=description),
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED

@pytest.mark.django_db
def test_create_task_requires_category(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    payload = _task_payload(category)
    del payload["category"]
    response = auth_client.post("/api/tasks/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "category" in response.data

@pytest.mark.django_db
def test_create_task_rejects_another_users_category(auth_client, test_user, other_user, category_factory):
    other_category = category_factory(user=other_user, name="Someone Else's")
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(other_category),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "category" in response.data

@pytest.mark.django_db
def test_create_task_requires_priority(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    payload = _task_payload(category)
    del payload["priority"]
    response = auth_client.post("/api/tasks/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "priority" in response.data

@pytest.mark.django_db
def test_create_task_rejects_start_time_in_the_past(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    past_start = timezone.now() - timedelta(hours=1)
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(
            category,
            start_time=past_start.isoformat(),
            end_time=(past_start + timedelta(hours=1)).isoformat(),
        ),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "start_time" in response.data

@pytest.mark.django_db
def test_create_task_rejects_end_time_before_start_time(auth_client, test_user, category_factory):
    category = category_factory(user=test_user)
    start = timezone.now() + timedelta(hours=2)
    response = auth_client.post(
        "/api/tasks/",
        _task_payload(category, start_time=start.isoformat(), end_time=(start - timedelta(hours=1)).isoformat()),
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "end_time" in response.data

@pytest.mark.django_db
def test_update_task_can_keep_past_start_time_when_untouched(auth_client, test_user, task_factory):
    # A task's start_time naturally becomes "the past" once its window
    # arrives -- editing an unrelated field (e.g. description) on an
    # already-started task must not be blocked by the past-time check.
    task = task_factory(
        user=test_user,
        status="In Progress",
        start_time=timezone.now() - timedelta(hours=1),
        end_time=timezone.now() + timedelta(hours=1),
    )
    response = auth_client.patch(
        f"/api/tasks/{task.id}/",
        {"description": "Updated notes"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.description == "Updated notes"

@pytest.mark.django_db
def test_update_task_full_payload_can_resend_unchanged_past_start_time(auth_client, test_user, category_factory, task_factory):
    # The task form always resends the whole object on save (not a partial
    # diff) -- editing an in-progress/overdue task must still work even
    # though start_time in that full payload is technically "in the past".
    category = category_factory(user=test_user)
    past_start = timezone.now() - timedelta(hours=1)
    future_end = timezone.now() + timedelta(hours=1)
    task = task_factory(
        user=test_user,
        category=category,
        status="In Progress",
        start_time=past_start,
        end_time=future_end,
    )
    response = auth_client.patch(
        f"/api/tasks/{task.id}/",
        _task_payload(
            category,
            title="Updated title",
            start_time=past_start.isoformat(),
            end_time=future_end.isoformat(),
        ),
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.title == "Updated title"

@pytest.mark.django_db
def test_update_task_rejects_changing_start_time_to_the_past(auth_client, test_user, category_factory, task_factory):
    category = category_factory(user=test_user)
    task = task_factory(
        user=test_user,
        category=category,
        status="Pending",
        start_time=timezone.now() + timedelta(hours=1),
        end_time=timezone.now() + timedelta(hours=2),
    )
    new_past_start = timezone.now() - timedelta(hours=1)
    response = auth_client.patch(
        f"/api/tasks/{task.id}/",
        {"start_time": new_past_start.isoformat()},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "start_time" in response.data

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
def test_stop_task_marks_it_completed(auth_client, task_factory):
    # "Stop" replaced the old separate "Complete" action -- ending an active
    # task now always means Completed, never a separate "Stopped" status.
    task = task_factory(status="In Progress")
    response = auth_client.post(f"/api/tasks/{task.id}/stop/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "Completed"
    assert task.completed_at is not None

@pytest.mark.django_db
def test_stop_task_from_paused_marks_it_completed(auth_client, task_factory):
    task = task_factory(status="Paused")
    response = auth_client.post(f"/api/tasks/{task.id}/stop/")
    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == "Completed"
    assert task.completed_at is not None

@pytest.mark.django_db
def test_stop_task_rejects_pending(auth_client, task_factory):
    task = task_factory(status="Pending")
    response = auth_client.post(f"/api/tasks/{task.id}/stop/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "Start the task before completing it."
    task.refresh_from_db()
    assert task.status == "Pending"

@pytest.mark.django_db
def test_stop_task_rejects_completed(auth_client, task_factory):
    task = task_factory(status="Completed")
    response = auth_client.post(f"/api/tasks/{task.id}/stop/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["message"] == "Task is already completed."
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

@pytest.mark.django_db
def test_reschedule_task_resets_overdue_reminder_flag(auth_client, task_factory):
    # Regression test: rescheduling an overdue task used to leave
    # reminder_overdue_sent=True, silently suppressing the overdue email
    # if the new deadline was also missed.
    task = task_factory(
        status="In Progress",
        reminder_30_sent=True,
        reminder_5_sent=True,
        reminder_progress_sent=True,
        reminder_overdue_sent=True,
        last_daily_reminder_date=timezone.localdate(),
    )
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
    assert task.reminder_30_sent is False
    assert task.reminder_5_sent is False
    assert task.reminder_progress_sent is False
    assert task.reminder_overdue_sent is False
    assert task.last_daily_reminder_date is None
