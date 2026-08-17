import pytest
from django.urls import reverse

from core import views


@pytest.fixture(autouse=True)
def _internal_task_key(settings):
    settings.INTERNAL_TASK_KEY = "test-internal-key"


def test_missing_key_returns_404(api_client):
    response = api_client.post(reverse("run-scheduled-tasks") + "?group=frequent")
    assert response.status_code == 404


def test_wrong_key_returns_404(api_client):
    response = api_client.post(
        reverse("run-scheduled-tasks") + "?group=frequent",
        HTTP_X_INTERNAL_TASK_KEY="wrong-key",
    )
    assert response.status_code == 404


def test_blank_configured_key_always_rejects(api_client, settings):
    # If INTERNAL_TASK_KEY is unset (e.g. forgotten on a fresh deploy), the
    # endpoint must stay closed rather than accepting an empty header value.
    settings.INTERNAL_TASK_KEY = ""
    response = api_client.post(
        reverse("run-scheduled-tasks") + "?group=frequent",
        HTTP_X_INTERNAL_TASK_KEY="",
    )
    assert response.status_code == 404


def test_correct_key_runs_named_group(api_client, monkeypatch):
    calls = []
    monkeypatch.setitem(views.JOB_GROUPS, "frequent", lambda: {"noop": lambda: calls.append("noop")})

    response = api_client.post(
        reverse("run-scheduled-tasks") + "?group=frequent",
        HTTP_X_INTERNAL_TASK_KEY="test-internal-key",
    )

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["results"]["noop"] == "ok"
    assert "noop" in response.data["duration_ms"]
    assert calls == ["noop"]


@pytest.mark.parametrize("group_name", ["frequent", "daily"])
def test_real_job_group_imports_cleanly_and_every_task_is_callable(group_name):
    # Guards against a future refactor accidentally breaking one of the
    # imports inside _frequent_jobs()/_daily_jobs() -- those are only
    # resolved lazily (inside the factory function) so a broken import
    # would otherwise stay silent until the next real cron run on Render.
    jobs = views.JOB_GROUPS[group_name]()
    assert jobs, f"{group_name} job group resolved to no tasks"
    for name, task_fn in jobs.items():
        assert callable(task_fn), f"{name} in {group_name!r} is not callable"


def test_correct_key_unknown_group_returns_400(api_client):
    response = api_client.post(
        reverse("run-scheduled-tasks") + "?group=bogus",
        HTTP_X_INTERNAL_TASK_KEY="test-internal-key",
    )
    assert response.status_code == 400


def test_task_exception_is_isolated_per_job(api_client, monkeypatch):
    def _boom():
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(
        views.JOB_GROUPS,
        "frequent",
        lambda: {"boom": _boom, "noop": lambda: None},
    )

    response = api_client.post(
        reverse("run-scheduled-tasks") + "?group=frequent",
        HTTP_X_INTERNAL_TASK_KEY="test-internal-key",
    )

    # One task failing must never stop -- or hide -- the rest of the group;
    # "noop" still ran, but the partial failure must be visible to the
    # GitHub Actions caller rather than silently reported as HTTP 200.
    assert response.status_code == 207
    assert response.data["success"] is False
    assert response.data["results"]["boom"] == "error"
    assert response.data["results"]["noop"] == "ok"


def test_all_tasks_failing_returns_500(api_client, monkeypatch):
    def _boom():
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(views.JOB_GROUPS, "frequent", lambda: {"boom": _boom, "boom2": _boom})

    response = api_client.post(
        reverse("run-scheduled-tasks") + "?group=frequent",
        HTTP_X_INTERNAL_TASK_KEY="test-internal-key",
    )

    # Every job in the group erroring points to something systemic (DB
    # down, bad deploy) rather than one flaky task -- worth a distinct,
    # harder failure signal than a partial one.
    assert response.status_code == 500
    assert response.data["success"] is False
    assert response.data["results"] == {"boom": "error", "boom2": "error"}


# ---------------------------------------------------------------------------
# GET /api/core/health/ -- public liveness/readiness probe used by
# scheduled-tasks.yml to wake a sleeping Render instance and wait for it to
# actually be ready before calling the authenticated endpoint above.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_health_endpoint_is_public(api_client):
    # No auth header at all -- this must work for an anonymous caller,
    # unlike run-scheduled-tasks.
    response = api_client.get(reverse("health"))
    assert response.status_code == 200
    assert response.data == {"status": "ok", "database": True}


def test_health_endpoint_reports_503_when_database_unreachable(api_client, monkeypatch):
    monkeypatch.setattr(views, "check_database", lambda: False)
    response = api_client.get(reverse("health"))
    assert response.status_code == 503
    assert response.data == {"status": "error", "database": False}


@pytest.mark.django_db
def test_health_endpoint_never_requires_internal_task_key(api_client, settings):
    # Sanity check against ever accidentally gating this behind the same
    # shared secret as run-scheduled-tasks -- it exists specifically so it
    # *doesn't* need one.
    settings.INTERNAL_TASK_KEY = "test-internal-key"
    response = api_client.get(reverse("health"))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Response body never leaks the configured secret, even on a rejected
# request (e.g. someone probing with a guessed key).
# ---------------------------------------------------------------------------

def test_response_body_never_contains_the_configured_key(api_client):
    response = api_client.post(
        reverse("run-scheduled-tasks") + "?group=frequent",
        HTTP_X_INTERNAL_TASK_KEY="wrong-key",
    )
    assert b"test-internal-key" not in response.content
