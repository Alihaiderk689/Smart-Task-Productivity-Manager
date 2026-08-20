from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework import status

from categories.models import Category
from tasks.models import Task
from usercopilot.services.category_resolver import create_category, list_category_names, resolve_category
from usercopilot.services.chat_service import ChatNotConfiguredError, UserChatService
from usercopilot.tools.base import ToolResult
from usercopilot.tools.registry import ToolRegistry, tool_registry
from usercopilot.tools.task_tools import (
    CompleteTaskTool,
    CreateTaskTool,
    DeleteTaskTool,
    GetProductivityInsightsTool,
    GetRemindersTool,
    GetTaskStatsTool,
    ListCategoriesTool,
    ListTasksTool,
    ReopenTaskTool,
    UpdateTaskTool,
    resolve_task,
)

# ---------------------------------------------------------------------------
# Registry -- structural guarantees
# ---------------------------------------------------------------------------

def test_registry_has_every_built_in_tool_registered():
    assert set(tool_registry.names()) == {
        "create_task", "update_task", "delete_task", "complete_task", "reopen_task",
        "list_tasks", "get_task_stats", "get_reminders", "get_productivity_insights",
        "list_categories",
    }

def test_no_tool_schema_exposes_a_user_or_user_id_field():
    # SECURITY: the LLM must never be able to even attempt to specify which
    # user's data to touch -- `user` is bound server-side at construction,
    # never a tool argument. This asserts that invariant structurally
    # rather than trusting every tool author to remember it by convention.
    for schema in tool_registry.schemas():
        props = schema["function"]["parameters"].get("properties", {})
        assert "user" not in props
        assert "user_id" not in props

@pytest.mark.django_db
def test_for_user_returns_fresh_instances_bound_to_that_user(test_user, other_user):
    tools_a = tool_registry.for_user(test_user)
    tools_b = tool_registry.for_user(other_user)
    assert tools_a["create_task"].user == test_user
    assert tools_b["create_task"].user == other_user
    assert tools_a["create_task"] is not tools_b["create_task"]

def test_registry_rejects_a_tool_class_with_no_name():
    class Nameless:
        name = ""
    with pytest.raises(ValueError):
        ToolRegistry().register(Nameless)

# ---------------------------------------------------------------------------
# category_resolver
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_resolve_category_matches_case_insensitively(test_user, category_factory):
    category_factory(name="Gym", user=test_user)
    assert resolve_category(test_user, "gym").name == "Gym"
    assert resolve_category(test_user, "GYM").name == "Gym"

@pytest.mark.django_db
def test_resolve_category_fuzzy_matches_a_typo(test_user, category_factory):
    category_factory(name="Personal", user=test_user)
    assert resolve_category(test_user, "Personel").name == "Personal"

@pytest.mark.django_db
def test_resolve_category_returns_none_for_no_match(test_user, category_factory):
    category_factory(name="Work", user=test_user)
    assert resolve_category(test_user, "Astrophysics") is None

@pytest.mark.django_db
def test_resolve_category_never_matches_another_users_category(test_user, other_user, category_factory):
    category_factory(name="Gym", user=other_user)
    assert resolve_category(test_user, "Gym") is None

@pytest.mark.django_db
def test_list_category_names_only_returns_own_categories(test_user, other_user, category_factory):
    category_factory(name="Mine", user=test_user)
    category_factory(name="Theirs", user=other_user)
    assert list_category_names(test_user) == ["Mine"]

# ---------------------------------------------------------------------------
# CreateTaskTool
# ---------------------------------------------------------------------------

def _iso(dt):
    return dt.isoformat()

@pytest.mark.django_db
def test_create_task_success(test_user, category_factory):
    category_factory(name="Gym", user=test_user)
    start = timezone.now() + timezone.timedelta(hours=1)
    end = start + timezone.timedelta(minutes=30)
    tool = CreateTaskTool(user=test_user)

    result = tool.run(title="Evening workout", category_name="gym", start_time=_iso(start), end_time=_iso(end))

    assert result.success is True
    assert Task.objects.filter(user=test_user, title="Evening workout").exists()
    assert result.data["category"] == "Gym"

@pytest.mark.django_db
def test_create_task_asks_before_creating_a_missing_category(test_user):
    start = timezone.now() + timezone.timedelta(hours=1)
    end = start + timezone.timedelta(minutes=30)
    tool = CreateTaskTool(user=test_user)

    result = tool.run(title="Read a book", category_name="Reading", start_time=_iso(start), end_time=_iso(end))

    assert result.success is True
    assert result.data["status"] == "needs_category_confirmation"
    assert not Category.objects.filter(user=test_user, name="Reading").exists()
    assert not Task.objects.filter(user=test_user).exists()

@pytest.mark.django_db
def test_create_task_creates_category_once_confirmed(test_user):
    start = timezone.now() + timezone.timedelta(hours=1)
    end = start + timezone.timedelta(minutes=30)
    tool = CreateTaskTool(user=test_user)

    result = tool.run(
        title="Read a book", category_name="Reading", start_time=_iso(start), end_time=_iso(end),
        create_category_if_missing=True,
    )

    assert result.success is True
    assert Category.objects.filter(user=test_user, name="Reading").exists()
    assert Task.objects.filter(user=test_user, title="Read a book").exists()

@pytest.mark.django_db
def test_create_task_rejects_gibberish_title(test_user, category_factory):
    category_factory(name="Work", user=test_user)
    start = timezone.now() + timezone.timedelta(hours=1)
    end = start + timezone.timedelta(minutes=30)
    tool = CreateTaskTool(user=test_user)

    result = tool.run(
        title="ahfuahsfua sfhasf uhaf uahf uashf auhfauhf",
        category_name="Work", start_time=_iso(start), end_time=_iso(end),
    )

    assert result.success is False
    assert not Task.objects.filter(user=test_user).exists()

@pytest.mark.django_db
def test_create_task_rejects_end_before_start(test_user, category_factory):
    category_factory(name="Work", user=test_user)
    start = timezone.now() + timezone.timedelta(hours=2)
    end = start - timezone.timedelta(hours=1)
    tool = CreateTaskTool(user=test_user)

    result = tool.run(title="Broken", category_name="Work", start_time=_iso(start), end_time=_iso(end))

    assert result.success is False

@pytest.mark.django_db
def test_create_task_rejects_malformed_datetime(test_user, category_factory):
    category_factory(name="Work", user=test_user)
    tool = CreateTaskTool(user=test_user)

    result = tool.run(title="Broken", category_name="Work", start_time="not-a-date", end_time="also-not-a-date")

    assert result.success is False

@pytest.mark.django_db
def test_create_task_schedules_reminders(test_user, category_factory):
    category_factory(name="Work", user=test_user)
    start = timezone.now() + timezone.timedelta(hours=1)
    end = start + timezone.timedelta(minutes=30)
    tool = CreateTaskTool(user=test_user)

    with patch("usercopilot.tools.task_tools.NotificationService.schedule_reminders") as mock_schedule:
        result = tool.run(title="Standup", category_name="Work", start_time=_iso(start), end_time=_iso(end))

    assert result.success is True
    mock_schedule.assert_called_once()


@pytest.mark.django_db
def test_create_task_succeeds_even_if_reminder_scheduling_fails(test_user, category_factory):
    category_factory(name="Work", user=test_user)
    start = timezone.now() + timezone.timedelta(hours=1)
    end = start + timezone.timedelta(minutes=30)
    tool = CreateTaskTool(user=test_user)

    with patch(
        "usercopilot.tools.task_tools.NotificationService.schedule_reminders",
        side_effect=ConnectionError("broker unreachable"),
    ):
        result = tool.run(title="Standup", category_name="Work", start_time=_iso(start), end_time=_iso(end))

    assert result.success is True
    assert result.data["status_note"] == "created, but reminders could not be scheduled"
    assert Task.objects.filter(user=test_user, title="Standup").exists()

# ---------------------------------------------------------------------------
# UpdateTaskTool
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_update_task_renames_by_title_query(test_user, task_factory):
    task_factory(title="assignment", user=test_user)
    tool = UpdateTaskTool(user=test_user)

    result = tool.run(title_query="assignment", new_title="AI Assignment")

    assert result.success is True
    assert Task.objects.get(user=test_user).title == "AI Assignment"

@pytest.mark.django_db
def test_update_task_changes_time(test_user, task_factory):
    task = task_factory(title="Meeting", user=test_user)
    new_start = task.start_time + timezone.timedelta(days=1)
    new_end = task.end_time + timezone.timedelta(days=1)
    tool = UpdateTaskTool(user=test_user)

    result = tool.run(task_id=task.id, new_start_time=_iso(new_start), new_end_time=_iso(new_end))

    assert result.success is True
    task.refresh_from_db()
    assert task.start_time == new_start

@pytest.mark.django_db
def test_update_task_time_change_regenerates_reminders(test_user, task_factory):
    from notifications.models import Reminder

    task = task_factory(
        title="Meeting", user=test_user,
        start_time=timezone.now() + timezone.timedelta(hours=2),
        end_time=timezone.now() + timezone.timedelta(hours=3),
        reminder_30_sent=True,
    )
    old_version = task.reminder_version
    new_start = timezone.now() + timezone.timedelta(days=1)
    new_end = new_start + timezone.timedelta(hours=1)
    tool = UpdateTaskTool(user=test_user)

    result = tool.run(task_id=task.id, new_start_time=_iso(new_start), new_end_time=_iso(new_end))

    assert result.success is True
    assert result.data["status_note"] == "updated, reminders rescheduled"
    task.refresh_from_db()
    assert task.reminder_version == old_version + 1
    assert task.reminder_30_sent is False
    assert Reminder.objects.filter(
        task=task, generation=task.reminder_version, status=Reminder.Status.PENDING,
    ).count() == 4


@pytest.mark.django_db
def test_update_task_without_time_change_does_not_touch_reminders(test_user, task_factory):
    task = task_factory(
        title="Meeting", user=test_user,
        start_time=timezone.now() + timezone.timedelta(hours=2),
        end_time=timezone.now() + timezone.timedelta(hours=3),
    )
    old_version = task.reminder_version
    tool = UpdateTaskTool(user=test_user)

    result = tool.run(task_id=task.id, new_title="Renamed meeting")

    assert result.success is True
    assert result.data["status_note"] == "updated"
    task.refresh_from_db()
    assert task.reminder_version == old_version

@pytest.mark.django_db
def test_update_task_with_nothing_to_change_asks_what(test_user, task_factory):
    task = task_factory(title="Meeting", user=test_user)
    tool = UpdateTaskTool(user=test_user)

    result = tool.run(task_id=task.id)

    assert result.success is False

@pytest.mark.django_db
def test_update_task_cannot_reach_another_users_task_by_id(test_user, other_user, task_factory):
    other_task = task_factory(title="Their task", user=other_user)
    tool = UpdateTaskTool(user=test_user)

    result = tool.run(task_id=other_task.id, new_title="Hijacked")

    assert result.success is False
    other_task.refresh_from_db()
    assert other_task.title == "Their task"

@pytest.mark.django_db
def test_update_task_title_query_never_matches_another_users_task(test_user, other_user, task_factory):
    task_factory(title="Distinctive gym session", user=other_user)
    tool = UpdateTaskTool(user=test_user)

    result = tool.run(title_query="Distinctive gym session", new_title="Hijacked")

    assert result.success is False

# ---------------------------------------------------------------------------
# DeleteTaskTool
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_delete_task_requires_confirmation_first(test_user, task_factory):
    task = task_factory(title="Old task", user=test_user)
    tool = DeleteTaskTool(user=test_user)

    result = tool.run(task_id=task.id, confirmed=False)

    assert result.success is True
    assert result.data["status"] == "needs_confirmation"
    assert Task.objects.filter(id=task.id).exists()

@pytest.mark.django_db
def test_delete_task_deletes_once_confirmed(test_user, task_factory):
    task = task_factory(title="Old task", user=test_user)
    tool = DeleteTaskTool(user=test_user)

    result = tool.run(task_id=task.id, confirmed=True)

    assert result.success is True
    assert not Task.objects.filter(id=task.id).exists()

@pytest.mark.django_db
def test_delete_task_cannot_delete_another_users_task(test_user, other_user, task_factory):
    other_task = task_factory(title="Their task", user=other_user)
    tool = DeleteTaskTool(user=test_user)

    result = tool.run(task_id=other_task.id, confirmed=True)

    assert result.success is False
    assert Task.objects.filter(id=other_task.id).exists()

# ---------------------------------------------------------------------------
# Complete / Reopen
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_complete_task_marks_completed_from_pending(test_user, task_factory):
    task = task_factory(title="Homework", user=test_user, status="Pending")
    tool = CompleteTaskTool(user=test_user)

    result = tool.run(task_id=task.id)

    assert result.success is True
    task.refresh_from_db()
    assert task.status == "Completed"
    assert task.completed_at is not None

@pytest.mark.django_db
def test_complete_task_cancels_pending_reminders(test_user, task_factory):
    from notifications.models import Reminder
    from notifications.reminder_processor import generate_reminders_for_task

    task = task_factory(
        title="Homework", user=test_user, status="Pending",
        start_time=timezone.now() + timezone.timedelta(hours=2),
        end_time=timezone.now() + timezone.timedelta(hours=3),
    )
    generate_reminders_for_task(task)
    assert Reminder.objects.filter(task=task, status=Reminder.Status.PENDING).count() == 4
    tool = CompleteTaskTool(user=test_user)

    result = tool.run(task_id=task.id)

    assert result.success is True
    assert not Reminder.objects.filter(task=task, status=Reminder.Status.PENDING).exists()
    assert Reminder.objects.filter(task=task, status=Reminder.Status.CANCELLED).count() == 4

@pytest.mark.django_db
def test_complete_task_already_completed_is_a_friendly_noop(test_user, task_factory):
    task = task_factory(title="Homework", user=test_user, status="Completed", completed_at=timezone.now())
    tool = CompleteTaskTool(user=test_user)

    result = tool.run(task_id=task.id)

    assert result.success is True
    assert result.data["status"] == "already_completed"

@pytest.mark.django_db
def test_complete_task_cannot_complete_another_users_task(test_user, other_user, task_factory):
    other_task = task_factory(title="Their task", user=other_user, status="Pending")
    tool = CompleteTaskTool(user=test_user)

    result = tool.run(task_id=other_task.id)

    assert result.success is False
    other_task.refresh_from_db()
    assert other_task.status == "Pending"

@pytest.mark.django_db
def test_reopen_task_resets_a_completed_task(test_user, task_factory):
    task = task_factory(title="Homework", user=test_user, status="Completed", completed_at=timezone.now(), started_at=timezone.now())
    tool = ReopenTaskTool(user=test_user)

    result = tool.run(task_id=task.id)

    assert result.success is True
    task.refresh_from_db()
    assert task.status == "Pending"
    assert task.completed_at is None

@pytest.mark.django_db
def test_reopen_task_refuses_a_task_that_isnt_completed(test_user, task_factory):
    task = task_factory(title="Homework", user=test_user, status="Pending")
    tool = ReopenTaskTool(user=test_user)

    result = tool.run(task_id=task.id)

    assert result.success is False

# ---------------------------------------------------------------------------
# resolve_task -- shared lookup used by update/delete/complete/reopen
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_resolve_task_ambiguous_title_lists_candidates_instead_of_guessing(test_user, task_factory):
    task_factory(title="Team meeting Monday", user=test_user)
    task_factory(title="Team meeting Friday", user=test_user)

    task, err = resolve_task(test_user, title_query="Team meeting")

    assert task is None
    assert "Monday" in err or "Friday" in err

@pytest.mark.django_db
def test_resolve_task_no_identifier_asks_which_task(test_user):
    task, err = resolve_task(test_user, task_id=None, title_query=None)
    assert task is None
    assert err

# ---------------------------------------------------------------------------
# ListTasksTool
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list_tasks_filters_by_when_overdue(test_user, task_factory):
    task_factory(
        title="Overdue", user=test_user, status="Pending",
        start_time=timezone.now() - timezone.timedelta(hours=3),
        end_time=timezone.now() - timezone.timedelta(hours=2),
    )
    task_factory(
        title="Future", user=test_user,
        start_time=timezone.now() + timezone.timedelta(hours=2),
        end_time=timezone.now() + timezone.timedelta(hours=3),
    )
    tool = ListTasksTool(user=test_user)

    result = tool.run(when="overdue")

    assert result.success is True
    titles = [t["title"] for t in result.data["tasks"]]
    assert titles == ["Overdue"]

@pytest.mark.django_db
def test_list_tasks_filters_by_keyword(test_user, task_factory):
    task_factory(title="React refactor", user=test_user)
    task_factory(title="Buy groceries", user=test_user)
    tool = ListTasksTool(user=test_user)

    result = tool.run(keyword="react")

    assert result.data["count"] == 1
    assert result.data["tasks"][0]["title"] == "React refactor"

@pytest.mark.django_db
def test_list_tasks_never_returns_another_users_tasks(test_user, other_user, task_factory):
    task_factory(title="Mine", user=test_user)
    task_factory(title="Theirs", user=other_user)
    tool = ListTasksTool(user=test_user)

    result = tool.run()

    titles = [t["title"] for t in result.data["tasks"]]
    assert titles == ["Mine"]

# ---------------------------------------------------------------------------
# Stats / reminders / insights -- cross-user isolation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_task_stats_only_counts_own_tasks(test_user, other_user, task_factory):
    task_factory(title="Mine 1", user=test_user, status="Completed", completed_at=timezone.now())
    task_factory(title="Mine 2", user=test_user, status="Pending")
    task_factory(title="Theirs", user=other_user, status="Completed", completed_at=timezone.now())

    result = GetTaskStatsTool(user=test_user).run()

    assert result.data["total_tasks"] == 2
    assert result.data["completion_rate_pct"] == 50.0

@pytest.mark.django_db
def test_get_reminders_only_considers_own_active_tasks(test_user, other_user, task_factory):
    task_factory(
        title="Mine soon", user=test_user, status="Pending",
        start_time=timezone.now() + timezone.timedelta(minutes=20),
        end_time=timezone.now() + timezone.timedelta(minutes=50),
    )
    task_factory(
        title="Theirs soon", user=other_user, status="Pending",
        start_time=timezone.now() + timezone.timedelta(minutes=20),
        end_time=timezone.now() + timezone.timedelta(minutes=50),
    )

    result = GetRemindersTool(user=test_user).run(when="today")

    tasks_mentioned = {r["task"] for r in result.data["reminders"]}
    assert "Theirs soon" not in tasks_mentioned

@pytest.mark.django_db
def test_get_reminders_ignores_completed_tasks(test_user, task_factory):
    task_factory(
        title="Done already", user=test_user, status="Completed", completed_at=timezone.now(),
        start_time=timezone.now() + timezone.timedelta(minutes=20),
        end_time=timezone.now() + timezone.timedelta(minutes=50),
    )
    result = GetRemindersTool(user=test_user).run()
    assert result.data["reminders"] == []

@pytest.mark.django_db
def test_get_productivity_insights_streak_counts_consecutive_days(test_user, task_factory):
    today = timezone.now()
    task_factory(title="Today", user=test_user, status="Completed", completed_at=today)
    task_factory(title="Yesterday", user=test_user, status="Completed", completed_at=today - timezone.timedelta(days=1))
    task_factory(title="3 days ago (gap)", user=test_user, status="Completed", completed_at=today - timezone.timedelta(days=3))

    result = GetProductivityInsightsTool(user=test_user).run()

    assert result.data["current_streak_days"] == 2

@pytest.mark.django_db
def test_get_productivity_insights_does_not_leak_another_users_category_breakdown(test_user, other_user, task_factory, category_factory):
    mine = category_factory(name="Mine", user=test_user)
    theirs = category_factory(name="Theirs", user=other_user)
    task_factory(title="Mine", user=test_user, category=mine)
    task_factory(title="Theirs", user=other_user, category=theirs)

    result = GetProductivityInsightsTool(user=test_user).run()

    categories_seen = {row["category"] for row in result.data["category_breakdown"]}
    assert categories_seen == {"Mine"}

@pytest.mark.django_db
def test_list_categories_scoped_to_user(test_user, other_user, category_factory):
    category_factory(name="Mine", user=test_user)
    category_factory(name="Theirs", user=other_user)

    result = ListCategoriesTool(user=test_user).run()

    assert result.data["categories"] == ["Mine"]

# ---------------------------------------------------------------------------
# Chat endpoint -- permissions, configuration, statelessness
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_chat_send_requires_authentication(api_client):
    response = api_client.post("/api/usercopilot/chat/send/", {"message": "hi"}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
def test_chat_send_works_for_a_regular_non_staff_user(auth_client, settings):
    # Unlike copilot (admin-only throughout), usercopilot is for ANY
    # authenticated user -- this is the key distinguishing permission test.
    settings.GROQ_API_KEY = "fake-key"
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Hello!", tool_calls=[]), finish_reason="stop")]
            )
        ))
    )
    from copilot.llm.client import GroqClient
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        response = auth_client.post("/api/usercopilot/chat/send/", {"message": "hi"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["reply"] == "Hello!"

@pytest.mark.django_db
def test_chat_send_returns_503_when_llm_not_configured(auth_client):
    response = auth_client.post("/api/usercopilot/chat/send/", {"message": "hi"}, format="json")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

@pytest.mark.django_db
def test_chat_send_rejects_empty_message(auth_client, settings):
    settings.GROQ_API_KEY = "fake-key"
    response = auth_client.post("/api/usercopilot/chat/send/", {"message": ""}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

def test_user_chat_service_not_configured_raises():
    from copilot.llm.client import GroqClient
    service = UserChatService(llm=GroqClient(api_key=""))
    with pytest.raises(ChatNotConfiguredError):
        service.send(user=SimpleNamespace(), message="hi")

@pytest.mark.django_db
def test_user_chat_service_executes_a_tool_call_end_to_end(test_user, task_factory):
    task_factory(title="Only task", user=test_user)
    from copilot.llm.client import GroqClient

    fake_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="list_tasks", arguments="{}"))
    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=[fake_call]), finish_reason="tool_calls"
            )])
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="You have 1 task: Only task.", tool_calls=[]), finish_reason="stop"
        )])

    fake_inner_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = UserChatService(llm=llm).send(user=test_user, message="what are my tasks?")

    assert result["reply"] == "You have 1 task: Only task."
    assert result["tool_calls"][0]["tool"] == "list_tasks"
    assert result["tool_calls"][0]["output"]["data"]["tasks"][0]["title"] == "Only task"

@pytest.mark.django_db
def test_user_chat_service_does_not_repeat_an_identical_tool_call_in_one_turn(test_user, category_factory):
    # Reproduces a real failure mode: after a rate-limited retry, the model
    # can see its own successful tool result and call the exact same
    # mutation again instead of just confirming -- create_task firing
    # twice for what was meant to be one task. Only the first call should
    # actually execute.
    category_factory(name="Work", user=test_user)
    from copilot.llm.client import GroqClient

    start = timezone.now() + timezone.timedelta(hours=1)
    end = start + timezone.timedelta(minutes=30)
    args = f'{{"title": "Standup", "category_name": "Work", "start_time": "{start.isoformat()}", "end_time": "{end.isoformat()}"}}'
    call_1 = SimpleNamespace(id="call_1", function=SimpleNamespace(name="create_task", arguments=args))
    call_2 = SimpleNamespace(id="call_2", function=SimpleNamespace(name="create_task", arguments=args))
    round_count = {"n": 0}

    def fake_create(**kwargs):
        round_count["n"] += 1
        if round_count["n"] == 1:
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=[call_1]), finish_reason="tool_calls"
            )])
        if round_count["n"] == 2:
            # The model, imperfectly, calls the identical create again.
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=[call_2]), finish_reason="tool_calls"
            )])
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="Created your Standup task.", tool_calls=[]), finish_reason="stop"
        )])

    fake_inner_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = UserChatService(llm=llm).send(user=test_user, message="Create a standup task")

    assert result["reply"] == "Created your Standup task."
    assert Task.objects.filter(user=test_user, title="Standup").count() == 1

@pytest.mark.django_db
def test_user_chat_service_tool_call_is_scoped_even_if_arguments_reference_another_user(test_user, other_user, task_factory):
    # SECURITY: even a hallucinated/adversarial tool call naming another
    # user's real task id must not be able to touch it -- resolve_task
    # filters on self.user regardless of what id the "LLM" supplied.
    other_task = task_factory(title="Not yours", user=other_user)
    from copilot.llm.client import GroqClient

    fake_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="complete_task", arguments=f'{{"task_id": {other_task.id}}}'),
    )
    fake_inner_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="", tool_calls=[fake_call]), finish_reason="tool_calls"
        )])
    )))
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        service = UserChatService(llm=llm)
        # only one round configured on the fake client -- call _run_tool directly via send()
        # but cap tool rounds so the fake (which never returns a final answer) doesn't loop forever
        with patch("usercopilot.services.chat_service.MAX_TOOL_ROUNDS", 1):
            service.send(user=test_user, message="mark it done")

    other_task.refresh_from_db()
    assert other_task.status != "Completed"
