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
    assert response.data["results"]["noop"] == "ok"
    assert calls == ["noop"]


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

    assert response.status_code == 200
    assert response.data["results"]["boom"] == "error"
    assert response.data["results"]["noop"] == "ok"
