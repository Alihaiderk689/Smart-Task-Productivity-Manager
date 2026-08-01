"""Locks in the API's authentication/authorization surface across every app.

This isn't testing for a known bug -- an audit of every view's
permission_classes/authentication_classes and every ORM lookup found the
project already gets this right everywhere (see PROTECTED_ENDPOINTS /
PUBLIC_ENDPOINTS below, which is the full endpoint inventory from every
urls.py). The point of this file is to make sure it *stays* right: without
it, nothing would catch a future change that accidentally drops a
permission_classes declaration, flips a global default, or swaps a
user-scoped queryset for an unscoped one -- until it became a real incident.
"""

import pytest
from django.contrib.auth.models import User
from django.conf import settings
from rest_framework import status

from categories.models import Category
from tasks.models import Task

# Every endpoint that must reject a request with no/invalid credentials.
# Deliberately an explicit, exhaustive list (not a loop over urlpatterns) --
# a new endpoint has to be added here on purpose, so an accidentally-public
# view can't slip through unnoticed.
PROTECTED_ENDPOINTS = [
    ("get", "/api/profile/"),
    ("patch", "/api/profile/"),
    ("post", "/api/profile/change-password/"),
    ("post", "/api/logout/"),
    ("get", "/api/tasks/"),
    ("post", "/api/tasks/"),
    ("get", "/api/tasks/1/"),
    ("patch", "/api/tasks/1/"),
    ("delete", "/api/tasks/1/"),
    ("post", "/api/tasks/1/start/"),
    ("post", "/api/tasks/1/pause/"),
    ("post", "/api/tasks/1/resume/"),
    ("post", "/api/tasks/1/stop/"),
    ("post", "/api/tasks/1/reschedule/"),
    ("get", "/api/categories/"),
    ("post", "/api/categories/"),
    ("get", "/api/categories/1/"),
    ("patch", "/api/categories/1/"),
    ("delete", "/api/categories/1/"),
    ("get", "/api/dashboard/summary/"),
    ("get", "/api/dashboard/today/"),
    ("get", "/api/dashboard/upcoming/"),
    ("get", "/api/dashboard/high-priority/"),
    ("get", "/api/dashboard/missed/"),
    ("get", "/api/analytics/productivity/"),
    ("get", "/api/analytics/weekly/"),
    ("get", "/api/analytics/monthly/"),
]

# Endpoints that must stay reachable with no credentials at all -- signup
# has nothing to authenticate yet, password-reset/verification links are
# clicked from an email, token/refresh trades a refresh token for a new
# access token before one exists.
PUBLIC_ENDPOINTS = [
    ("get", "/api/hello/"),
    ("post", "/api/signup/"),
    ("post", "/api/login/"),
    ("post", "/api/google-login/"),
    ("post", "/api/verify-email/"),
    ("post", "/api/verify-email/resend/"),
    ("post", "/api/password-reset/"),
    ("post", "/api/password-reset/confirm/"),
    ("post", "/api/token/refresh/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", PROTECTED_ENDPOINTS)
def test_protected_endpoint_rejects_unauthenticated_request(api_client, method, url):
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
        f"{method.upper()} {url} should require authentication, got {response.status_code}"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", PROTECTED_ENDPOINTS)
def test_protected_endpoint_rejects_garbage_token(api_client, method, url):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", PUBLIC_ENDPOINTS)
def test_public_endpoint_does_not_require_authentication(api_client, method, url):
    response = getattr(api_client, method)(url, {}, format="json")
    # Whatever else happens (400 for a missing field, etc.), it must never
    # be blocked purely for lacking auth -- that would mean someone
    # accidentally locked down an endpoint meant to be public.
    assert response.status_code != status.HTTP_401_UNAUTHORIZED


def test_global_defaults_are_still_locked_down():
    # If either of these ever changes, every endpoint above that relies on
    # the *global* default (rather than its own explicit permission_classes)
    # silently changes behavior with it. This fails loudly instead.
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == (
        "rest_framework.permissions.IsAuthenticated",
    )
    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    )


# ---------------------------------------------------------------------------
# Object-level authorization: being logged in is necessary but not
# sufficient -- these prove user A's valid session still can't reach user
# B's data by guessing/knowing an ID.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cannot_view_another_users_task(auth_client, other_user, task_factory):
    other_task = task_factory(user=other_user)

    response = auth_client.get(f"/api/tasks/{other_task.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cannot_edit_another_users_task(auth_client, other_user, task_factory):
    other_task = task_factory(user=other_user, title="Not yours")

    response = auth_client.patch(f"/api/tasks/{other_task.id}/", {"title": "Hijacked"}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    other_task.refresh_from_db()
    assert other_task.title == "Not yours"


@pytest.mark.django_db
def test_cannot_delete_another_users_task(auth_client, other_user, task_factory):
    other_task = task_factory(user=other_user)

    response = auth_client.delete(f"/api/tasks/{other_task.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Task.objects.filter(id=other_task.id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["start", "pause", "resume", "stop", "reschedule"])
def test_cannot_run_lifecycle_actions_on_another_users_task(auth_client, other_user, task_factory, action):
    other_task = task_factory(user=other_user, status="Pending")

    response = auth_client.post(f"/api/tasks/{other_task.id}/{action}/", {}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    other_task.refresh_from_db()
    assert other_task.status == "Pending"  # untouched


@pytest.mark.django_db
def test_task_list_never_includes_another_users_tasks(auth_client, test_user, other_user, task_factory):
    task_factory(user=test_user, title="Mine")
    task_factory(user=other_user, title="Not mine")

    response = auth_client.get("/api/tasks/")

    assert response.status_code == status.HTTP_200_OK
    titles = [t["title"] for t in response.data]
    assert titles == ["Mine"]


@pytest.mark.django_db
def test_cannot_view_another_users_category(auth_client, other_user, category_factory):
    other_category = category_factory(user=other_user, name="Not yours")

    response = auth_client.get(f"/api/categories/{other_category.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cannot_delete_another_users_category(auth_client, other_user, category_factory):
    other_category = category_factory(user=other_user)

    response = auth_client.delete(f"/api/categories/{other_category.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Category.objects.filter(id=other_category.id).exists()


@pytest.mark.django_db
def test_dashboard_only_reflects_the_authenticated_users_tasks(auth_client, test_user, other_user, task_factory):
    task_factory(user=test_user, status="Completed")
    task_factory(user=other_user, status="Completed")
    task_factory(user=other_user, status="Completed")

    response = auth_client.get("/api/dashboard/summary/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["completed_tasks"] == 1
