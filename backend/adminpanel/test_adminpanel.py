from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone
from rest_framework import status

from tasks.models import Task

ADMIN_ENDPOINTS = [
    ("get", "/api/admin/overview/"),
    ("get", "/api/admin/system-status/"),
    ("get", "/api/admin/users/"),
    ("get", "/api/admin/users/1/"),
    ("get", "/api/admin/users/1/tasks/"),
    ("post", "/api/admin/users/1/deactivate/"),
    ("post", "/api/admin/users/1/activate/"),
    ("delete", "/api/admin/users/1/delete/"),
    ("get", "/api/admin/categories/names/"),
    ("get", "/api/admin/tasks/"),
    ("get", "/api/admin/tasks/1/"),
    ("patch", "/api/admin/tasks/1/"),
    ("delete", "/api/admin/tasks/1/"),
    ("post", "/api/admin/tasks/1/trigger-reminder/"),
    ("get", "/api/admin/reports/users.csv"),
    ("get", "/api/admin/reports/tasks.csv"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", ADMIN_ENDPOINTS)
def test_admin_endpoints_reject_unauthenticated(api_client, method, url):
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", ADMIN_ENDPOINTS)
def test_admin_endpoints_reject_non_staff_user(auth_client, method, url):
    response = getattr(auth_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_overview_counts(staff_client, test_user, other_user, task_factory):
    task_factory(user=test_user, status="Completed")
    task_factory(user=other_user, status="Pending")
    task_factory(user=other_user, status="Pending")

    response = staff_client.get("/api/admin/overview/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_users"] == User.objects.count()
    assert response.data["active_users"] == User.objects.filter(is_active=True).count()
    assert response.data["total_tasks"] == 3
    assert response.data["tasks_by_status"]["Pending"] == 2
    assert response.data["tasks_by_status"]["Completed"] == 1


@pytest.mark.django_db
def test_admin_user_list_includes_task_counts(staff_client, test_user, other_user, task_factory):
    task_factory(user=test_user)
    task_factory(user=test_user)

    response = staff_client.get("/api/admin/users/")

    assert response.status_code == status.HTTP_200_OK
    by_email = {row["email"]: row for row in response.data["results"]}
    assert by_email[test_user.email]["task_count"] == 2
    assert by_email[other_user.email]["task_count"] == 0


@pytest.mark.django_db
def test_admin_user_list_search(staff_client, test_user, other_user):
    response = staff_client.get(f"/api/admin/users/?search={test_user.email}")

    assert response.status_code == status.HTTP_200_OK
    emails = [row["email"] for row in response.data["results"]]
    assert test_user.email in emails
    assert other_user.email not in emails


@pytest.mark.django_db
def test_admin_user_tasks_scoped_to_that_user(staff_client, test_user, other_user, task_factory):
    task_factory(user=test_user, title="Mine")
    task_factory(user=other_user, title="Not mine")

    response = staff_client.get(f"/api/admin/users/{test_user.id}/tasks/")

    assert response.status_code == status.HTTP_200_OK
    titles = [t["title"] for t in response.data["results"]]
    assert titles == ["Mine"]


@pytest.mark.django_db
def test_admin_user_tasks_404_for_unknown_user(staff_client):
    response = staff_client.get("/api/admin/users/999999/tasks/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_deactivate_user_success(staff_client, test_user):
    response = staff_client.post(f"/api/admin/users/{test_user.id}/deactivate/")

    assert response.status_code == status.HTTP_200_OK
    test_user.refresh_from_db()
    assert test_user.is_active is False


@pytest.mark.django_db
def test_admin_cannot_deactivate_own_account(staff_client, staff_user):
    response = staff_client.post(f"/api/admin/users/{staff_user.id}/deactivate/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    staff_user.refresh_from_db()
    assert staff_user.is_active is True


@pytest.mark.django_db
def test_admin_cannot_deactivate_a_superuser(staff_client, test_user):
    test_user.is_superuser = True
    test_user.save(update_fields=["is_superuser"])

    response = staff_client.post(f"/api/admin/users/{test_user.id}/deactivate/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    test_user.refresh_from_db()
    assert test_user.is_active is True


@pytest.mark.django_db
def test_admin_activate_user_success(staff_client, test_user):
    test_user.is_active = False
    test_user.save(update_fields=["is_active"])

    response = staff_client.post(f"/api/admin/users/{test_user.id}/activate/")

    assert response.status_code == status.HTTP_200_OK
    test_user.refresh_from_db()
    assert test_user.is_active is True


@pytest.mark.django_db
def test_admin_delete_task_success(staff_client, test_user, task_factory):
    task = task_factory(user=test_user)

    response = staff_client.delete(f"/api/admin/tasks/{task.id}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Task.objects.filter(id=task.id).exists()


@pytest.mark.django_db
def test_admin_delete_task_404_for_unknown_task(staff_client):
    response = staff_client.delete("/api/admin/tasks/999999/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Overview: overdue count + week-over-week
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_overview_overdue_count(staff_client, test_user, task_factory):
    now = timezone.now()
    task_factory(user=test_user, status="Pending", start_time=now - timedelta(days=2), end_time=now - timedelta(days=1))
    task_factory(user=test_user, status="Completed", start_time=now - timedelta(days=2), end_time=now - timedelta(days=1))
    task_factory(user=test_user, status="Pending", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))

    response = staff_client.get("/api/admin/overview/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["overdue_tasks"] == 1


@pytest.mark.django_db
def test_admin_overview_week_over_week_users(staff_client, test_user):
    User.objects.filter(pk=test_user.pk).update(date_joined=timezone.now() - timedelta(days=10))

    response = staff_client.get("/api/admin/overview/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["new_users_previous_7_days"] >= 1


@pytest.mark.django_db
def test_admin_overview_week_over_week_completed_tasks(staff_client, test_user, task_factory):
    now = timezone.now()
    recent = task_factory(user=test_user, status="Completed", start_time=now - timedelta(hours=3), end_time=now - timedelta(hours=2))
    recent.completed_at = now - timedelta(days=1)
    recent.save(update_fields=["completed_at"])

    older = task_factory(user=test_user, status="Completed", start_time=now - timedelta(days=10), end_time=now - timedelta(days=9))
    older.completed_at = now - timedelta(days=10)
    older.save(update_fields=["completed_at"])

    response = staff_client.get("/api/admin/overview/")

    assert response.data["tasks_completed_last_7_days"] == 1
    assert response.data["tasks_completed_previous_7_days"] == 1


# ---------------------------------------------------------------------------
# User detail + delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_user_detail(staff_client, test_user, task_factory):
    task_factory(user=test_user)

    response = staff_client.get(f"/api/admin/users/{test_user.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == test_user.email
    assert response.data["task_count"] == 1
    assert "avatar" in response.data


@pytest.mark.django_db
def test_admin_user_detail_404_for_unknown_user(staff_client):
    response = staff_client.get("/api/admin/users/999999/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_delete_user_success(staff_client, test_user):
    user_id = test_user.id
    response = staff_client.delete(f"/api/admin/users/{user_id}/delete/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not User.objects.filter(id=user_id).exists()


@pytest.mark.django_db
def test_admin_cannot_delete_own_account(staff_client, staff_user):
    response = staff_client.delete(f"/api/admin/users/{staff_user.id}/delete/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert User.objects.filter(id=staff_user.id).exists()


@pytest.mark.django_db
def test_admin_cannot_delete_a_superuser(staff_client, test_user):
    test_user.is_superuser = True
    test_user.save(update_fields=["is_superuser"])

    response = staff_client.delete(f"/api/admin/users/{test_user.id}/delete/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert User.objects.filter(id=test_user.id).exists()


# ---------------------------------------------------------------------------
# Global task list
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_task_list_includes_every_users_tasks(staff_client, test_user, other_user, task_factory):
    task_factory(user=test_user, title="Mine")
    task_factory(user=other_user, title="Not mine")

    response = staff_client.get("/api/admin/tasks/")

    assert response.status_code == status.HTTP_200_OK
    titles = {t["title"] for t in response.data["results"]}
    assert {"Mine", "Not mine"} <= titles


@pytest.mark.django_db
def test_admin_task_list_search(staff_client, test_user, task_factory):
    task_factory(user=test_user, title="Quarterly report")
    task_factory(user=test_user, title="Buy groceries")

    response = staff_client.get("/api/admin/tasks/?search=quarterly")

    assert response.status_code == status.HTTP_200_OK
    titles = [t["title"] for t in response.data["results"]]
    assert titles == ["Quarterly report"]


@pytest.mark.django_db
def test_admin_task_list_filter_by_status(staff_client, test_user, task_factory):
    task_factory(user=test_user, status="Pending")
    task_factory(user=test_user, status="Completed")

    response = staff_client.get("/api/admin/tasks/?status=Completed")

    assert response.status_code == status.HTTP_200_OK
    assert all(t["status"] == "Completed" for t in response.data["results"])
    assert len(response.data["results"]) == 1


@pytest.mark.django_db
def test_admin_task_list_filter_by_category(staff_client, test_user, category_factory, task_factory):
    cat_a = category_factory(user=test_user, name="Work")
    cat_b = category_factory(user=test_user, name="Personal")
    task_factory(user=test_user, category=cat_a, title="Work task")
    task_factory(user=test_user, category=cat_b, title="Personal task")

    response = staff_client.get(f"/api/admin/tasks/?category={cat_a.id}")

    assert response.status_code == status.HTTP_200_OK
    titles = [t["title"] for t in response.data["results"]]
    assert titles == ["Work task"]


@pytest.mark.django_db
def test_admin_task_list_overdue_filter(staff_client, test_user, task_factory):
    now = timezone.now()
    task_factory(user=test_user, status="Pending", title="Overdue", start_time=now - timedelta(days=2), end_time=now - timedelta(days=1))
    task_factory(user=test_user, status="Pending", title="Future", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2))
    task_factory(user=test_user, status="Completed", title="Done late", start_time=now - timedelta(days=2), end_time=now - timedelta(days=1))

    response = staff_client.get("/api/admin/tasks/?overdue=true")

    assert response.status_code == status.HTTP_200_OK
    titles = [t["title"] for t in response.data["results"]]
    assert titles == ["Overdue"]


@pytest.mark.django_db
def test_admin_task_list_filter_by_category_name_across_users(staff_client, test_user, other_user, category_factory, task_factory):
    my_work = category_factory(user=test_user, name="Work")
    their_work = category_factory(user=other_user, name="Work")
    my_personal = category_factory(user=test_user, name="Personal")

    task_factory(user=test_user, category=my_work, title="My work task")
    task_factory(user=other_user, category=their_work, title="Their work task")
    task_factory(user=test_user, category=my_personal, title="My personal task")

    response = staff_client.get("/api/admin/tasks/?category_name=work")

    assert response.status_code == status.HTTP_200_OK
    titles = {t["title"] for t in response.data["results"]}
    assert titles == {"My work task", "Their work task"}


@pytest.mark.django_db
def test_admin_category_names_are_distinct_across_users(staff_client, test_user, other_user, category_factory):
    category_factory(user=test_user, name="Work")
    category_factory(user=other_user, name="Work")
    category_factory(user=test_user, name="Personal")

    response = staff_client.get("/api/admin/categories/names/")

    assert response.status_code == status.HTTP_200_OK
    assert sorted(response.data) == ["Personal", "Work"]


@pytest.mark.django_db
def test_admin_task_list_filter_by_user(staff_client, test_user, other_user, task_factory):
    task_factory(user=test_user, title="Mine")
    task_factory(user=other_user, title="Not mine")

    response = staff_client.get(f"/api/admin/tasks/?user={test_user.id}")

    assert response.status_code == status.HTTP_200_OK
    titles = [t["title"] for t in response.data["results"]]
    assert titles == ["Mine"]


# ---------------------------------------------------------------------------
# Task detail: retrieve/edit
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_task_detail_get(staff_client, test_user, task_factory):
    task = task_factory(user=test_user, title="Look at me")

    response = staff_client.get(f"/api/admin/tasks/{task.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["title"] == "Look at me"
    assert response.data["user_email"] == test_user.email


@pytest.mark.django_db
def test_admin_task_edit_success(staff_client, test_user, task_factory):
    task = task_factory(user=test_user, title="Old title")

    response = staff_client.patch(f"/api/admin/tasks/{task.id}/", {"title": "New title"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.title == "New title"


@pytest.mark.django_db
def test_admin_task_edit_rejects_title_over_word_limit(staff_client, test_user, task_factory):
    task = task_factory(user=test_user)
    long_title = " ".join(["word"] * 21)

    response = staff_client.patch(f"/api/admin/tasks/{task.id}/", {"title": long_title}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "title" in response.data


@pytest.mark.django_db
def test_admin_task_edit_rejects_category_from_a_different_user(staff_client, test_user, other_user, task_factory, category_factory):
    task = task_factory(user=test_user)
    other_users_category = category_factory(user=other_user, name="Not test_user's")

    response = staff_client.patch(f"/api/admin/tasks/{task.id}/", {"category": other_users_category.id}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "category" in response.data


@pytest.mark.django_db
def test_admin_task_edit_rejects_end_before_start(staff_client, test_user, task_factory):
    now = timezone.now()
    task = task_factory(user=test_user, start_time=now, end_time=now + timedelta(hours=1))

    response = staff_client.patch(
        f"/api/admin/tasks/{task.id}/",
        {"end_time": (now - timedelta(hours=1)).isoformat()},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "end_time" in response.data


@pytest.mark.django_db
def test_admin_task_edit_allows_backdating_start_time(staff_client, test_user, task_factory):
    # Unlike the regular user-facing serializer, the admin path doesn't
    # block a past start_time -- an admin may legitimately need to correct
    # a task's schedule after the fact.
    task = task_factory(user=test_user)
    past_start = timezone.now() - timedelta(days=5)

    response = staff_client.patch(
        f"/api/admin/tasks/{task.id}/",
        {"start_time": past_start.isoformat()},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Trigger reminder
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_trigger_reminder_invalid_type(staff_client, test_user, task_factory):
    task = task_factory(user=test_user)

    response = staff_client.post(f"/api/admin/tasks/{task.id}/trigger-reminder/", {"type": "not-a-type"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_trigger_reminder_overdue_sends_email_and_marks_missed(staff_client, test_user, task_factory):
    now = timezone.now()
    task = task_factory(
        user=test_user, status="Pending",
        start_time=now - timedelta(hours=2), end_time=now - timedelta(hours=1),
    )

    response = staff_client.post(f"/api/admin/tasks/{task.id}/trigger-reminder/", {"type": "overdue"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["sent"] is True
    assert len(mail.outbox) == 1
    task.refresh_from_db()
    assert task.reminder_overdue_sent is True
    assert task.status == "Missed"


@pytest.mark.django_db
def test_trigger_reminder_does_not_resend_already_sent(staff_client, test_user, task_factory):
    # "Already sent" is now tracked by the Reminder row's own status (see
    # notifications/reminder_processor.py) rather than Task.reminder_30_sent
    # directly -- that boolean is just a denormalized read cache the
    # processor updates alongside the real state, so the real state (a
    # SENT Reminder row) is what has to exist here for this to be a
    # faithful test of the "don't resend" guarantee.
    from notifications.models import Reminder

    task = task_factory(user=test_user, status="Pending", reminder_30_sent=True)
    Reminder.objects.create(
        task=task, kind=Reminder.Kind.THIRTY_MIN, scheduled_for=timezone.now(),
        generation=task.reminder_version, status=Reminder.Status.SENT, sent_at=timezone.now(),
    )

    response = staff_client.post(f"/api/admin/tasks/{task.id}/trigger-reminder/", {"type": "30min"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["sent"] is False
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_trigger_reminder_reports_not_sent_when_task_does_not_qualify(staff_client, test_user, task_factory):
    task = task_factory(user=test_user, status="Completed")

    response = staff_client.post(f"/api/admin/tasks/{task.id}/trigger-reminder/", {"type": "30min"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["sent"] is False
    assert len(mail.outbox) == 0


# ---------------------------------------------------------------------------
# CSV reports
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_export_users_csv(staff_client, test_user):
    response = staff_client.get("/api/admin/reports/users.csv")

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "text/csv"
    content = response.content.decode()
    assert test_user.email in content


@pytest.mark.django_db
def test_export_tasks_csv(staff_client, test_user, task_factory):
    task_factory(user=test_user, title="Exportable task")

    response = staff_client.get("/api/admin/reports/tasks.csv")

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "text/csv"
    content = response.content.decode()
    assert "Exportable task" in content


# ---------------------------------------------------------------------------
# System status
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_system_status_structure(staff_client):
    response = staff_client.get("/api/admin/system-status/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["api"]["ok"] is True
    assert response.data["database"]["ok"] is True
    assert "ok" in response.data["redis"]
    assert "ok" in response.data["celery"]


@pytest.mark.django_db
def test_system_status_redis_ok_when_reachable(staff_client, monkeypatch):
    class FakeRedisClient:
        def ping(self):
            return True

    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: FakeRedisClient())

    response = staff_client.get("/api/admin/system-status/")

    assert response.data["redis"]["ok"] is True


@pytest.mark.django_db
def test_system_status_redis_not_ok_when_unreachable(staff_client, monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("no redis")

    monkeypatch.setattr("redis.Redis.from_url", _raise)

    response = staff_client.get("/api/admin/system-status/")

    assert response.data["redis"]["ok"] is False


@pytest.mark.django_db
def test_system_status_celery_workers_reported(staff_client, monkeypatch):
    class FakeInspect:
        def ping(self):
            return {"worker1@host": {"ok": "pong"}}

    class FakeControl:
        def inspect(self, timeout=1):
            return FakeInspect()

    class FakeCeleryApp:
        control = FakeControl()

    monkeypatch.setattr("config.celery.app", FakeCeleryApp())

    response = staff_client.get("/api/admin/system-status/")

    assert response.data["celery"]["ok"] is True
    assert "worker1@host" in response.data["celery"]["workers"]
