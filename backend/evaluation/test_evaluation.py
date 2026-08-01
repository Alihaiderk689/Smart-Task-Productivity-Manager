import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework import status

from categories.models import Category
from copilot.agents.system_health import SystemHealthAgent
from copilot.llm.client import GroqClient
from copilot.models import Recommendation
from copilot.tools.base import PlannedStep
from evaluation import runner
from evaluation.fixtures import EvalFixtures
from evaluation.metrics import compute_metrics
from evaluation.models import EvalCaseResult, EvaluationRun
from evaluation.runner import run_full_evaluation
from tasks.models import Task


def _fake_groq_response(content="Hello!", tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


class _Result:
    """Stand-in for EvalCaseResult, used to unit-test metrics.py's pure math
    without touching the database."""

    def __init__(self, **kwargs):
        self.passed = kwargs.get("passed", False)
        self.category = kwargs.get("category", "task_visibility")
        self.response_time_ms = kwargs.get("response_time_ms", 0)
        self.tool_selection_correct = kwargs.get("tool_selection_correct")
        self.planning_correct = kwargs.get("planning_correct")
        self.permission_correct = kwargs.get("permission_correct")
        self.hallucination_detected = kwargs.get("hallucination_detected")
        self.error_recovered = kwargs.get("error_recovered")


# ---------------------------------------------------------------------------
# metrics.py
# ---------------------------------------------------------------------------

def test_compute_metrics_empty_list():
    metrics = compute_metrics([])
    assert metrics["total_cases"] == 0
    assert metrics["task_success_rate"] is None
    assert metrics["tool_selection_accuracy"] is None
    assert metrics["avg_response_time_ms"] is None


def test_compute_metrics_task_success_rate():
    results = [_Result(passed=True), _Result(passed=True), _Result(passed=False)]
    metrics = compute_metrics(results)
    assert metrics["total_cases"] == 3
    assert metrics["passed_cases"] == 2
    assert metrics["failed_cases"] == 1
    assert metrics["task_success_rate"] == pytest.approx(66.7, abs=0.1)


def test_compute_metrics_dimension_only_averages_applicable_cases():
    results = [
        _Result(passed=True, tool_selection_correct=True),
        _Result(passed=True, tool_selection_correct=True),
        _Result(passed=False, tool_selection_correct=False),
        _Result(passed=True, tool_selection_correct=None),  # not applicable -- must not affect the denominator
    ]
    metrics = compute_metrics(results)
    assert metrics["tool_selection_accuracy"] == pytest.approx(66.7, abs=0.1)


def test_compute_metrics_hallucination_rate_is_a_bad_rate():
    results = [_Result(passed=True, hallucination_detected=False), _Result(passed=False, hallucination_detected=True)]
    metrics = compute_metrics(results)
    assert metrics["hallucination_rate"] == 50.0


def test_compute_metrics_workflow_completion_rate_only_counts_workflow_category():
    results = [
        _Result(passed=True, category="workflow"),
        _Result(passed=False, category="workflow"),
        _Result(passed=True, category="analytics"),
    ]
    metrics = compute_metrics(results)
    assert metrics["workflow_completion_rate"] == 50.0


def test_compute_metrics_avg_response_time():
    results = [_Result(passed=True, response_time_ms=100), _Result(passed=True, response_time_ms=300)]
    metrics = compute_metrics(results)
    assert metrics["avg_response_time_ms"] == 200.0


def test_compute_metrics_cases_by_category():
    results = [
        _Result(passed=True, category="analytics"),
        _Result(passed=False, category="analytics"),
        _Result(passed=True, category="workflow"),
    ]
    metrics = compute_metrics(results)
    assert metrics["cases_by_category"]["analytics"] == {"passed": 1, "failed": 1}
    assert metrics["cases_by_category"]["workflow"] == {"passed": 1, "failed": 0}


# ---------------------------------------------------------------------------
# fixtures.py
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_eval_fixtures_creates_and_cleans_up_everything():
    fx = EvalFixtures()
    user = fx.dormant_user(days_inactive=100)
    other = fx.regular_user()
    task = fx.overdue_task(user=user, minutes_overdue=5)
    old_task = fx.old_completed_task(user=other, days_ago=40)
    rec = Recommendation.objects.create(title="x", description="", category="users", status="pending")
    fx.track_recommendation(rec.id)

    assert User.objects.filter(id__in=[user.id, other.id]).count() == 2
    assert Task.objects.filter(id__in=[task.id, old_task.id]).count() == 2

    fx.cleanup()

    assert User.objects.filter(id__in=[user.id, other.id]).count() == 0
    assert Task.objects.filter(id__in=[task.id, old_task.id]).count() == 0
    assert Recommendation.objects.filter(id=rec.id).exists() is False
    assert Category.objects.filter(user_id__in=[user.id, other.id]).count() == 0


@pytest.mark.django_db
def test_eval_fixtures_dormant_user_has_stale_last_login():
    from django.utils import timezone
    fx = EvalFixtures()
    user = fx.dormant_user(days_inactive=120)
    assert user.last_login < timezone.now() - timezone.timedelta(days=100)
    fx.cleanup()


@pytest.mark.django_db
def test_eval_fixtures_overdue_task_is_actually_overdue():
    from django.utils import timezone
    fx = EvalFixtures()
    user = fx.regular_user()
    task = fx.overdue_task(user=user, minutes_overdue=10)
    assert task.end_time < timezone.now()
    assert task.status == "Pending"
    fx.cleanup()


@pytest.mark.django_db
def test_eval_fixtures_cleanup_does_not_touch_unrelated_data(test_user):
    fx = EvalFixtures()
    fx.regular_user()
    fx.cleanup()
    assert User.objects.filter(id=test_user.id).exists()


# ---------------------------------------------------------------------------
# runner.py -- deterministic agent-run scenarios (no LLM needed)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_run_agent_scenario_passes_for_system_health():
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=True), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        case = runner._run_agent_scenario("system_health_agent_run", "x", "system_maintenance", SystemHealthAgent)

    assert case["passed"] is True
    assert case["tool_selection_correct"] is True
    assert case["planning_correct"] is True
    assert case["actual"]["tools_in_order"] == ["check_database", "check_redis", "check_celery_workers"]


@pytest.mark.django_db
def test_run_agent_scenario_fails_when_plan_deviates():
    class BrokenAgent(SystemHealthAgent):
        def plan(self, observation, reasoning):
            return [PlannedStep(tool_name="check_database")]  # missing two expected steps

    with patch("copilot.tools.system_tools.check_database", return_value=True):
        case = runner._run_agent_scenario("x", "x", "system_maintenance", BrokenAgent)

    assert case["passed"] is False
    assert case["tool_selection_correct"] is False


# ---------------------------------------------------------------------------
# runner.py -- permission-boundary scenarios
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_permission_chat_non_admin_scenario_passes_when_blocked():
    fx = EvalFixtures()
    case = runner.scenario_permission_chat_non_admin(fx)
    fx.cleanup()
    assert case["passed"] is True
    assert case["permission_correct"] is True


@pytest.mark.django_db
def test_permission_run_agent_non_admin_scenario_passes_when_blocked():
    fx = EvalFixtures()
    case = runner.scenario_permission_run_agent_non_admin(fx)
    fx.cleanup()
    assert case["passed"] is True


# ---------------------------------------------------------------------------
# runner.py -- failure-injection scenarios
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_failure_database_check_down_scenario_recovers():
    case = runner.scenario_failure_database_check_down()
    assert case["passed"] is True
    assert case["error_recovered"] is True


@pytest.mark.django_db
def test_failure_redis_exception_scenario_recovers():
    case = runner.scenario_failure_redis_exception_mid_agent()
    assert case["passed"] is True
    assert case["actual"]["tool_call_count"] == 3


@pytest.mark.django_db
def test_failure_tool_exception_mid_plan_scenario_recovers():
    case = runner.scenario_failure_tool_exception_mid_plan()
    assert case["passed"] is True


@pytest.mark.django_db
def test_failure_llm_outage_chat_scenario_recovers(staff_user, settings):
    settings.GROQ_API_KEY = "fake-key-for-test"
    case = runner.scenario_failure_llm_outage_chat(staff_user)
    assert case["passed"] is True
    assert case["actual"]["status_code"] == 200


# ---------------------------------------------------------------------------
# runner.py -- chat scenarios (LLM mocked)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_view_overdue_tasks_chat_scenario_passes_with_correct_tool_and_number(staff_user, task_factory, settings):
    from django.utils import timezone
    task_factory(status="Pending", end_time=timezone.now() - timezone.timedelta(hours=1))
    settings.GROQ_API_KEY = "fake-key-for-test"

    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="list_overdue_tasks", arguments="{}"))
    responses = [
        _fake_groq_response(content="", tool_calls=[call]),
        _fake_groq_response(content="There is 1 overdue task right now."),
    ]
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: responses.pop(0))))
    with patch.object(GroqClient, "_get_client", return_value=fake_client):
        case = runner.scenario_view_overdue_tasks_chat(staff_user)

    assert case["tool_selection_correct"] is True
    assert case["hallucination_detected"] is False
    assert case["passed"] is True


@pytest.mark.django_db
def test_view_overdue_tasks_chat_scenario_leaves_hallucination_none_when_tool_never_called(staff_user, settings):
    # An outage (or any turn where the model never calls the tool) has no
    # claim to check -- it must not be scored as a hallucination just
    # because it didn't answer.
    settings.GROQ_API_KEY = "fake-key-for-test"
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: _fake_groq_response("I don't know."))))
    with patch.object(GroqClient, "_get_client", return_value=fake_client):
        case = runner.scenario_view_overdue_tasks_chat(staff_user)

    assert case["tool_selection_correct"] is False
    assert case["hallucination_detected"] is None
    assert case["passed"] is False


@pytest.mark.django_db
def test_user_deactivate_chat_permission_scenario_fails_if_model_mutates_directly(staff_user, settings):
    settings.GROQ_API_KEY = "fake-key-for-test"
    fx = EvalFixtures()

    # A deliberately unsafe fake model that calls the sensitive tool by name
    # directly -- proves the scenario's grading catches it rather than just
    # trusting the model's behavior.
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="deactivate_user", arguments='{"user_id": 1}'))
    responses = [
        _fake_groq_response(content="", tool_calls=[call]),
        _fake_groq_response(content="Done, I deactivated them."),
    ]
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: responses.pop(0))))
    with patch.object(GroqClient, "_get_client", return_value=fake_client):
        case = runner.scenario_user_deactivate_chat_permission(staff_user, fx)
    fx.cleanup()

    assert case["permission_correct"] is False
    assert case["passed"] is False


@pytest.mark.django_db
def test_user_deactivate_chat_permission_scenario_passes_when_model_proposes_instead(staff_user, settings):
    settings.GROQ_API_KEY = "fake-key-for-test"
    fx = EvalFixtures()

    def fake_create(**kwargs):
        if getattr(fake_create, "_called", False):
            return _fake_groq_response(content="I've proposed that for approval.")
        fake_create._called = True
        user_message = next(m["content"] for m in kwargs["messages"] if m["role"] == "user")
        user_id = int(re.search(r"id (\d+)", user_message).group(1))
        call = SimpleNamespace(
            id="c1",
            function=SimpleNamespace(
                name="propose_action",
                arguments=(
                    '{"title": "Deactivate dormant user", "description": "d", "tool": "deactivate_user", '
                    f'"tool_input": {{"user_id": {user_id}}}, "category": "users", "risk": "medium"}}'
                ),
            ),
        )
        return _fake_groq_response(content="", tool_calls=[call])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    with patch.object(GroqClient, "_get_client", return_value=fake_client):
        case = runner.scenario_user_deactivate_chat_permission(staff_user, fx)
    fx.cleanup()

    assert case["permission_correct"] is True
    assert case["passed"] is True


# ---------------------------------------------------------------------------
# runner.py -- full orchestration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_run_full_evaluation_creates_all_cases_and_cleans_up_fixtures(staff_user, settings):
    settings.GROQ_API_KEY = "fake-key-for-test"
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Here's what I found.")))
    )
    users_before = set(User.objects.values_list("id", flat=True))

    with patch.object(GroqClient, "_get_client", return_value=fake_client):
        run = run_full_evaluation(triggered_by=staff_user)

    assert run.status == "completed"
    assert run.total_cases == 22
    assert run.case_results.count() == 22
    assert set(run.metrics.keys()) >= {
        "task_success_rate", "tool_selection_accuracy", "planning_accuracy", "permission_accuracy",
        "hallucination_rate", "error_recovery_rate", "avg_response_time_ms", "workflow_completion_rate",
    }

    # Agent-driven workflows don't depend on the LLM calling the right tool
    # (the proposal itself is deterministic Python), so they should pass
    # even under this generic no-tool-call fake model.
    workflow_cases = {c.scenario_id: c for c in run.case_results.filter(category="workflow")}
    assert workflow_cases["workflow_dormant_user_cleanup"].passed is True
    assert workflow_cases["workflow_missed_reminder_remediation"].passed is True

    leftover_fixture_users = User.objects.filter(email__startswith="eval-fixture-").exclude(id__in=users_before)
    assert leftover_fixture_users.count() == 0


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

EVAL_ENDPOINTS = [
    ("post", "/api/evaluation/run/"),
    ("get", "/api/evaluation/runs/"),
    ("get", "/api/evaluation/runs/1/"),
    ("get", "/api/evaluation/summary/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", EVAL_ENDPOINTS)
def test_evaluation_endpoints_reject_unauthenticated(api_client, method, url):
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", EVAL_ENDPOINTS)
def test_evaluation_endpoints_reject_non_staff(auth_client, method, url):
    response = getattr(auth_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_evaluation_run_list_and_detail_endpoints(staff_client):
    run = EvaluationRun.objects.create(
        status="completed", total_cases=2, passed_cases=1, failed_cases=1, metrics={"task_success_rate": 50.0}
    )
    EvalCaseResult.objects.create(run=run, scenario_id="a", scenario_name="A", category="analytics", passed=True)
    EvalCaseResult.objects.create(run=run, scenario_id="b", scenario_name="B", category="analytics", passed=False)

    list_response = staff_client.get("/api/evaluation/runs/")
    assert list_response.status_code == status.HTTP_200_OK
    assert len(list_response.data) == 1
    assert "case_results" not in list_response.data[0]

    detail_response = staff_client.get(f"/api/evaluation/runs/{run.id}/")
    assert detail_response.status_code == status.HTTP_200_OK
    assert len(detail_response.data["case_results"]) == 2


@pytest.mark.django_db
def test_evaluation_summary_endpoint(staff_client):
    EvaluationRun.objects.create(
        status="completed", total_cases=5, passed_cases=4, failed_cases=1, metrics={"task_success_rate": 80.0}
    )

    response = staff_client.get("/api/evaluation/summary/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["latest"]["metrics"]["task_success_rate"] == 80.0
    assert len(response.data["trend"]) == 1


@pytest.mark.django_db
def test_evaluation_summary_endpoint_with_no_runs(staff_client):
    response = staff_client.get("/api/evaluation/summary/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["latest"] is None
    assert response.data["trend"] == []


@pytest.mark.django_db
def test_trigger_evaluation_endpoint_runs_and_persists(staff_client, settings):
    settings.GROQ_API_KEY = "fake-key-for-test"
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("info"))))
    with patch.object(GroqClient, "_get_client", return_value=fake_client):
        response = staff_client.post("/api/evaluation/run/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_cases"] == 22
    assert EvaluationRun.objects.count() == 1
