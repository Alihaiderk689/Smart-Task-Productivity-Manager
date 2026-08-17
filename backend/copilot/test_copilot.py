from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from django.contrib.auth.models import User
from groq import RateLimitError
from rest_framework import status

from copilot.agents.action import ActionAgent
from copilot.agents.analytics import AnalyticsAgent
from copilot.agents.database_intelligence import DatabaseIntelligenceAgent
from copilot.agents.recommendation import RecommendationAgent
from copilot.agents.reminder import ReminderAgent
from copilot.agents.system_health import SystemHealthAgent
from copilot.agents.task_intelligence import TaskIntelligenceAgent
from copilot.agents.user_monitoring import UserMonitoringAgent
from copilot.llm.client import ChatResult, GroqClient, LLMNotConfiguredError
from copilot.llm.fallback_client import LLMClient
from copilot.llm.gemini_client import GeminiClient, GeminiNotConfiguredError
from copilot.llm.openrouter_client import OpenRouterClient, OpenRouterNotConfiguredError
from copilot.memory.service import MemoryService
from copilot.models import AgentRun, ConversationMessage, Recommendation, ToolCallLog
from copilot.repositories import AgentRunRepository, RecommendationRepository
from copilot.services.chat_service import ChatNotConfiguredError, ChatService
from copilot.tools.action_tools import ProposeActionTool
from copilot.tools.analytics_tools import GetCategoryBreakdownTool, GetProductivityTrendsTool, GetTaskStatsTool
from copilot.tools.base import BaseTool, PlannedStep, ToolResult
from copilot.tools.database_tools import FindDuplicateCategoriesTool, GetCopilotActivityStatsTool, GetDatabaseStatsTool
from copilot.tools.registry import ToolNotFoundError, ToolRegistry
from copilot.tools.reminder_tools import ListReminderCandidatesTool, SendReminderTool
from copilot.tools.system_tools import CheckCeleryWorkersTool, CheckDatabaseTool, CheckRedisTool
from copilot.tools.task_tools import (
    DeleteCompletedTasksTool,
    GetTaskCompletionByCategoryTool,
    ListOverdueTasksTool,
    ListStalePendingTasksTool,
)
from copilot.tools.user_tools import (
    DeactivateUserTool,
    DeleteUserTool,
    GetUserGrowthStatsTool,
    ListAllUsersTool,
    ListInactiveUsersTool,
    RenameUserTool,
)
from tasks.models import Task

# ---------------------------------------------------------------------------
# Tools + registry
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_check_database_tool_success():
    result = CheckDatabaseTool().run()
    assert result.success is True
    assert result.data == {"ok": True}


def test_check_redis_tool_reports_failure():
    with patch("copilot.tools.system_tools.check_redis", return_value=False):
        result = CheckRedisTool().run()
    assert result.success is False
    assert "not reachable" in result.error


def test_check_celery_workers_tool_reports_failure_when_no_workers():
    with patch("copilot.tools.system_tools.check_celery_workers", return_value=[]):
        result = CheckCeleryWorkersTool().run()
    assert result.success is False
    assert result.data == {"workers": []}


def test_check_celery_workers_tool_success():
    with patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1@host"]):
        result = CheckCeleryWorkersTool().run()
    assert result.success is True
    assert result.data == {"workers": ["worker1@host"]}


def test_tool_registry_register_and_get():
    registry = ToolRegistry()
    tool = CheckDatabaseTool()
    registry.register(tool)
    assert registry.get("check_database") is tool
    assert "check_database" in registry
    assert registry.names() == ["check_database"]
    assert len(registry) == 1


def test_tool_registry_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("nonexistent")


def test_tool_registry_rejects_unnamed_tool():
    class UnnamedTool(BaseTool):
        name = ""
        def run(self, **kwargs):
            return ToolResult(success=True)

    with pytest.raises(ValueError):
        ToolRegistry().register(UnnamedTool())


def test_tool_to_llm_schema_shape():
    schema = CheckDatabaseTool().to_llm_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "check_database"
    assert "parameters" in schema["function"]


def test_tool_registry_as_llm_schema_lists_every_tool():
    registry = ToolRegistry()
    registry.register(CheckDatabaseTool())
    registry.register(CheckRedisTool())
    schemas = registry.as_llm_schema()
    assert {s["function"]["name"] for s in schemas} == {"check_database", "check_redis"}


def test_built_in_tools_registered_on_app_ready():
    # apps.py's ready() should have registered these against the shared
    # module-level registry by the time tests run (Django calls ready()
    # during app startup).
    from copilot.tools.registry import tool_registry
    assert {"check_database", "check_redis", "check_celery_workers"} <= set(tool_registry.names())


# ---------------------------------------------------------------------------
# GroqClient
# ---------------------------------------------------------------------------

def test_groq_client_not_configured_without_key():
    client = GroqClient(api_key="")
    assert client.is_configured is False


def test_groq_client_configured_with_key():
    client = GroqClient(api_key="fake-key")
    assert client.is_configured is True


def test_groq_client_chat_raises_when_not_configured():
    client = GroqClient(api_key="")
    with pytest.raises(LLMNotConfiguredError):
        client.chat([{"role": "user", "content": "hi"}])


def _fake_groq_response(content="Hello!", tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _fake_rate_limit_error():
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def test_groq_client_chat_parses_plain_text_response():
    client = GroqClient(api_key="fake-key")
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Hi there")))
    )
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "hi"}])

    assert isinstance(result, ChatResult)
    assert result.content == "Hi there"
    assert result.wants_tool_call is False


def test_groq_client_chat_parses_tool_calls():
    client = GroqClient(api_key="fake-key")
    fake_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="check_database", arguments="{}"))
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response(content="", tool_calls=[fake_call])
        ))
    )
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "check the db"}], tools=[CheckDatabaseTool().to_llm_schema()])

    assert result.wants_tool_call is True
    assert result.tool_calls[0].name == "check_database"
    assert result.tool_calls[0].arguments == {}


def test_groq_client_chat_normalizes_null_arguments_to_empty_dict():
    # Groq sometimes emits the literal string "null" as a no-arg tool call's
    # arguments -- valid JSON, but not an object, so it must still become {}
    # rather than None (which would blow up a caller's **arguments).
    client = GroqClient(api_key="fake-key")
    fake_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="check_database", arguments="null"))
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response(content="", tool_calls=[fake_call])
        ))
    )
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "check the db"}], tools=[CheckDatabaseTool().to_llm_schema()])

    assert result.tool_calls[0].arguments == {}


def test_groq_client_summarize_returns_content():
    client = GroqClient(api_key="fake-key")
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("A summary.")))
    )
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        text = client.summarize("Summarize this")

    assert text == "A summary."


# ---------------------------------------------------------------------------
# GeminiClient -- Gemini fallback, same OpenAI-compatible response shape as Groq
# ---------------------------------------------------------------------------

def test_gemini_client_not_configured_without_key():
    client = GeminiClient(api_key="")
    assert client.is_configured is False


def test_gemini_client_configured_with_key():
    client = GeminiClient(api_key="fake-key")
    assert client.is_configured is True


def test_gemini_client_chat_raises_when_not_configured():
    client = GeminiClient(api_key="")
    with pytest.raises(GeminiNotConfiguredError):
        client.chat([{"role": "user", "content": "hi"}])


def test_gemini_client_chat_parses_plain_text_response():
    client = GeminiClient(api_key="fake-key")
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Hi from Gemini")))
    )
    with patch.object(GeminiClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "hi"}])

    assert isinstance(result, ChatResult)
    assert result.content == "Hi from Gemini"
    assert result.wants_tool_call is False


def test_gemini_client_chat_parses_tool_calls():
    client = GeminiClient(api_key="fake-key")
    fake_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="check_database", arguments="{}"))
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response(content="", tool_calls=[fake_call])
        ))
    )
    with patch.object(GeminiClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "check the db"}], tools=[CheckDatabaseTool().to_llm_schema()])

    assert result.wants_tool_call is True
    assert result.tool_calls[0].name == "check_database"
    assert result.tool_calls[0].arguments == {}


def test_gemini_client_chat_normalizes_null_arguments_to_empty_dict():
    client = GeminiClient(api_key="fake-key")
    fake_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="check_database", arguments="null"))
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response(content="", tool_calls=[fake_call])
        ))
    )
    with patch.object(GeminiClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "check the db"}], tools=[CheckDatabaseTool().to_llm_schema()])

    assert result.tool_calls[0].arguments == {}


# ---------------------------------------------------------------------------
# OpenRouterClient -- third fallback, same OpenAI-compatible response shape
# as Groq/Gemini
# ---------------------------------------------------------------------------

def test_openrouter_client_not_configured_without_key():
    client = OpenRouterClient(api_key="")
    assert client.is_configured is False


def test_openrouter_client_configured_with_key():
    client = OpenRouterClient(api_key="fake-key")
    assert client.is_configured is True


def test_openrouter_client_chat_raises_when_not_configured():
    client = OpenRouterClient(api_key="")
    with pytest.raises(OpenRouterNotConfiguredError):
        client.chat([{"role": "user", "content": "hi"}])


def test_openrouter_client_chat_parses_plain_text_response():
    client = OpenRouterClient(api_key="fake-key")
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Hi from OpenRouter")))
    )
    with patch.object(OpenRouterClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "hi"}])

    assert isinstance(result, ChatResult)
    assert result.content == "Hi from OpenRouter"
    assert result.wants_tool_call is False


def test_openrouter_client_chat_parses_tool_calls():
    client = OpenRouterClient(api_key="fake-key")
    fake_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="check_database", arguments="{}"))
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response(content="", tool_calls=[fake_call])
        ))
    )
    with patch.object(OpenRouterClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "check the db"}], tools=[CheckDatabaseTool().to_llm_schema()])

    assert result.wants_tool_call is True
    assert result.tool_calls[0].name == "check_database"
    assert result.tool_calls[0].arguments == {}


def test_openrouter_client_chat_normalizes_null_arguments_to_empty_dict():
    client = OpenRouterClient(api_key="fake-key")
    fake_call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="check_database", arguments="null"))
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response(content="", tool_calls=[fake_call])
        ))
    )
    with patch.object(OpenRouterClient, "_get_client", return_value=fake_inner_client):
        result = client.chat([{"role": "user", "content": "check the db"}], tools=[CheckDatabaseTool().to_llm_schema()])

    assert result.tool_calls[0].arguments == {}


# ---------------------------------------------------------------------------
# LLMClient -- Groq -> Gemini -> OpenRouter fallback orchestration
# (fallback_client.py). Retry/backoff/fallback policy all lives here now,
# not in either ChatService -- see
# test_chat_service_llm_outage_returns_graceful_reply_not_exception below
# for how a chat service reacts once LLMClient gives up entirely.
# ---------------------------------------------------------------------------

def test_llm_client_is_configured_true_if_only_groq_configured():
    llm = LLMClient(groq=GroqClient(api_key="fake-key"), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key=""))
    assert llm.is_configured is True


def test_llm_client_is_configured_true_if_only_gemini_configured():
    llm = LLMClient(groq=GroqClient(api_key=""), gemini=GeminiClient(api_key="fake-key"), openrouter=OpenRouterClient(api_key=""))
    assert llm.is_configured is True


def test_llm_client_is_configured_true_if_only_openrouter_configured():
    llm = LLMClient(groq=GroqClient(api_key=""), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key="fake-key"))
    assert llm.is_configured is True


def test_llm_client_is_configured_false_if_none_configured():
    llm = LLMClient(groq=GroqClient(api_key=""), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key=""))
    assert llm.is_configured is False


def test_llm_client_chat_raises_when_no_provider_configured():
    llm = LLMClient(groq=GroqClient(api_key=""), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key=""))
    with pytest.raises(LLMNotConfiguredError):
        llm.chat([{"role": "user", "content": "hi"}])


def test_llm_client_chat_retries_transient_error_before_succeeding():
    attempts = {"n": 0}

    def flaky_create(**kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("transient network error")
        return _fake_groq_response("Recovered on retry.")

    fake_inner_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=flaky_create)))
    llm = LLMClient(groq=GroqClient(api_key="fake-key"), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key=""))
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = llm.chat([{"role": "user", "content": "hello"}])

    assert result.content == "Recovered on retry."
    assert attempts["n"] == 2


def test_llm_client_chat_backs_off_and_recovers_from_rate_limit():
    # A burst of chat traffic (or the eval suite's ~20 back-to-back scenarios)
    # can trip Groq's per-minute limit well before the daily quota is
    # actually exhausted -- the right response is to wait it out across a
    # couple of attempts rather than immediately degrading to the outage
    # fallback with zero tool calls.
    attempts = {"n": 0}

    def flaky_create(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _fake_rate_limit_error()
        return _fake_groq_response("Recovered after rate-limit backoff.")

    fake_inner_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=flaky_create)))
    llm = LLMClient(groq=GroqClient(api_key="fake-key"), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key=""))
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client), \
         patch("copilot.llm.fallback_client.time.sleep") as mock_sleep:
        result = llm.chat([{"role": "user", "content": "hello"}])

    assert result.content == "Recovered after rate-limit backoff."
    assert attempts["n"] == 3
    # Backed off before both retries, not just once.
    assert mock_sleep.call_count == 2


def test_llm_client_chat_falls_back_to_gemini_when_groq_exhausted():
    fake_groq_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("groq is unreachable"))
        ))
    )
    fake_gemini_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Handled by Gemini.")))
    )
    llm = LLMClient(groq=GroqClient(api_key="fake-key"), gemini=GeminiClient(api_key="fake-gemini-key"), openrouter=OpenRouterClient(api_key=""))
    with patch.object(GroqClient, "_get_client", return_value=fake_groq_inner), \
         patch.object(GeminiClient, "_get_client", return_value=fake_gemini_inner):
        result = llm.chat([{"role": "user", "content": "hello"}])

    assert result.content == "Handled by Gemini."


def test_llm_client_chat_goes_straight_to_gemini_when_groq_unconfigured():
    fake_gemini_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Handled by Gemini.")))
    )
    llm = LLMClient(groq=GroqClient(api_key=""), gemini=GeminiClient(api_key="fake-gemini-key"), openrouter=OpenRouterClient(api_key=""))
    with patch.object(GeminiClient, "_get_client", return_value=fake_gemini_inner):
        result = llm.chat([{"role": "user", "content": "hello"}])

    assert result.content == "Handled by Gemini."


def test_llm_client_chat_falls_back_to_openrouter_when_groq_and_gemini_exhausted():
    fake_groq_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("groq is unreachable"))
        ))
    )
    fake_gemini_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("gemini is unreachable"))
        ))
    )
    fake_openrouter_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Handled by OpenRouter.")))
    )
    llm = LLMClient(
        groq=GroqClient(api_key="fake-key"),
        gemini=GeminiClient(api_key="fake-gemini-key"),
        openrouter=OpenRouterClient(api_key="fake-openrouter-key"),
    )
    with patch.object(GroqClient, "_get_client", return_value=fake_groq_inner), \
         patch.object(GeminiClient, "_get_client", return_value=fake_gemini_inner), \
         patch.object(OpenRouterClient, "_get_client", return_value=fake_openrouter_inner):
        result = llm.chat([{"role": "user", "content": "hello"}])

    assert result.content == "Handled by OpenRouter."


def test_llm_client_chat_goes_straight_to_openrouter_when_groq_and_gemini_unconfigured():
    fake_openrouter_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("Handled by OpenRouter.")))
    )
    llm = LLMClient(
        groq=GroqClient(api_key=""),
        gemini=GeminiClient(api_key=""),
        openrouter=OpenRouterClient(api_key="fake-openrouter-key"),
    )
    with patch.object(OpenRouterClient, "_get_client", return_value=fake_openrouter_inner):
        result = llm.chat([{"role": "user", "content": "hello"}])

    assert result.content == "Handled by OpenRouter."


def test_llm_client_chat_reraises_original_groq_error_when_gemini_not_configured():
    fake_groq_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("groq is unreachable"))
        ))
    )
    llm = LLMClient(groq=GroqClient(api_key="fake-key"), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key=""))
    with patch.object(GroqClient, "_get_client", return_value=fake_groq_inner):
        with pytest.raises(ConnectionError):
            llm.chat([{"role": "user", "content": "hello"}])


def test_llm_client_chat_reraises_last_providers_error_when_all_three_fail():
    fake_groq_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("groq is unreachable"))
        ))
    )
    fake_gemini_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("gemini is unreachable"))
        ))
    )
    fake_openrouter_inner = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(TimeoutError("openrouter is unreachable"))
        ))
    )
    llm = LLMClient(
        groq=GroqClient(api_key="fake-key"),
        gemini=GeminiClient(api_key="fake-gemini-key"),
        openrouter=OpenRouterClient(api_key="fake-openrouter-key"),
    )
    with patch.object(GroqClient, "_get_client", return_value=fake_groq_inner), \
         patch.object(GeminiClient, "_get_client", return_value=fake_gemini_inner), \
         patch.object(OpenRouterClient, "_get_client", return_value=fake_openrouter_inner):
        # The chain exhausts every configured provider -- the error the
        # caller sees is whichever one failed last (OpenRouter here), not
        # Groq's original error, since ChatService/UserChatService only
        # care that nothing could serve the request at all.
        with pytest.raises(TimeoutError):
            llm.chat([{"role": "user", "content": "hello"}])


def test_llm_client_summarize_returns_content():
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: _fake_groq_response("A summary.")))
    )
    llm = LLMClient(groq=GroqClient(api_key="fake-key"), gemini=GeminiClient(api_key=""), openrouter=OpenRouterClient(api_key=""))
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        text = llm.summarize("Summarize this")

    assert text == "A summary."


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_agent_run_repository_lifecycle(test_user):
    repo = AgentRunRepository()
    run = repo.start(agent_name="system_health", trigger="manual", requested_by=test_user)
    assert run.status == "running"

    result = ToolResult(success=True, data={"ok": True})
    log = repo.log_tool_call(run, tool_name="check_database", tool_input={}, result=result)
    assert log.success is True
    assert log.output_data == {"ok": True}

    completed = repo.complete(run, observation_summary="obs", reasoning_summary="reason", plan=[], result_summary="done", confidence=0.9)
    assert completed.status == "completed"
    assert completed.finished_at is not None
    assert completed.confidence == 0.9


@pytest.mark.django_db
def test_agent_run_repository_fail():
    repo = AgentRunRepository()
    run = repo.start(agent_name="system_health", trigger="manual")
    failed = repo.fail(run, error="boom")
    assert failed.status == "failed"
    assert failed.error == "boom"


@pytest.mark.django_db
def test_agent_run_repository_last_for_returns_most_recent():
    repo = AgentRunRepository()
    repo.start(agent_name="system_health", trigger="manual")
    second = repo.start(agent_name="system_health", trigger="manual")
    assert repo.last_for("system_health").id == second.id
    assert repo.last_for("nonexistent_agent") is None


@pytest.mark.django_db
def test_recommendation_repository_pending_filters_by_category():
    repo = RecommendationRepository()
    repo.create(title="A", description="", category="system", status="pending")
    repo.create(title="B", description="", category="users", status="pending")
    repo.create(title="C", description="", category="system", status="approved")

    pending_system = repo.pending(category="system")
    assert [r.title for r in pending_system] == ["A"]


# ---------------------------------------------------------------------------
# Memory service
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_memory_service_add_and_recent_history(test_user):
    memory = MemoryService()
    memory.add_message(user=test_user, content="show inactive users", role="admin")
    memory.add_message(user=test_user, content="Here you go.", role="agent")

    history = memory.recent_history(user=test_user)
    assert [m.content for m in history] == ["show inactive users", "Here you go."]


@pytest.mark.django_db
def test_memory_service_sessions_are_isolated(test_user):
    memory = MemoryService()
    memory.add_message(user=test_user, content="session A msg", role="admin", session_id="a")
    memory.add_message(user=test_user, content="session B msg", role="admin", session_id="b")

    assert [m.content for m in memory.recent_history(user=test_user, session_id="a")] == ["session A msg"]


@pytest.mark.django_db
def test_memory_service_to_llm_messages_maps_roles(test_user):
    memory = MemoryService()
    memory.add_message(user=test_user, content="hi", role="admin")
    memory.add_message(user=test_user, content="hello", role="agent")

    messages = memory.to_llm_messages(user=test_user)
    assert messages == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]


# ---------------------------------------------------------------------------
# SystemHealthAgent (end-to-end through BaseAgent.run())
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_system_health_agent_all_healthy():
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=True), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        run = SystemHealthAgent().run(trigger="manual")

    assert run.status == "completed"
    assert run.confidence == 1.0
    assert "operational" in run.result_summary
    assert run.tool_calls.count() == 3
    assert run.recommendations.count() == 0


@pytest.mark.django_db
def test_system_health_agent_creates_recommendation_on_failure():
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=False), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        run = SystemHealthAgent().run(trigger="manual")

    assert run.status == "completed"  # the agent itself succeeded at detecting the problem
    assert run.confidence < 1.0
    assert "Issues detected" in run.result_summary

    assert run.recommendations.count() == 1
    rec = run.recommendations.first()
    assert rec.category == "system"
    assert rec.risk == "high"
    assert rec.status == "pending"
    assert rec.requires_approval is False  # observation-only alert, nothing to approve


@pytest.mark.django_db
def test_system_health_agent_logs_every_tool_call_with_duration():
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=True), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        run = SystemHealthAgent().run(trigger="manual")

    tool_names = set(run.tool_calls.values_list("tool_name", flat=True))
    assert tool_names == {"check_database", "check_redis", "check_celery_workers"}
    assert all(tc.duration_ms >= 0 for tc in run.tool_calls.all())


@pytest.mark.django_db
def test_system_health_agent_run_persists_agent_run_row():
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=True), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        run = SystemHealthAgent().run(trigger="scheduled")

    assert AgentRun.objects.filter(id=run.id, agent_name="system_health", trigger="scheduled").exists()


@pytest.mark.django_db
def test_agent_run_marked_failed_when_plan_references_unknown_tool():
    class BrokenAgent(SystemHealthAgent):
        def plan(self, observation, reasoning):
            return [PlannedStep(tool_name="does_not_exist")]

    run = BrokenAgent().run(trigger="manual")

    assert run.status == "failed"
    assert run.error  # non-empty


@pytest.mark.django_db
def test_system_health_agent_uses_llm_summary_when_configured():
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response("Everything looks great, chief.")
        ))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client), \
         patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=True), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        run = SystemHealthAgent(llm=llm).run(trigger="manual")

    assert run.result_summary == "Everything looks great, chief."


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

COPILOT_ENDPOINTS = [
    ("get", "/api/copilot/agent-status/"),
    ("post", "/api/copilot/agents/system_health/run/"),
    ("get", "/api/copilot/runs/"),
    ("get", "/api/copilot/runs/1/"),
    ("get", "/api/copilot/recommendations/"),
    ("get", "/api/copilot/dashboard-summary/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", COPILOT_ENDPOINTS)
def test_copilot_endpoints_reject_unauthenticated(api_client, method, url):
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", COPILOT_ENDPOINTS)
def test_copilot_endpoints_reject_non_staff(auth_client, method, url):
    response = getattr(auth_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_agent_status_endpoint_lists_system_health(staff_client):
    response = staff_client.get("/api/copilot/agent-status/")

    assert response.status_code == status.HTTP_200_OK
    names = [row["name"] for row in response.data]
    assert "system_health" in names
    entry = next(row for row in response.data if row["name"] == "system_health")
    assert entry["last_run"] is None  # nothing has run yet


@pytest.mark.django_db
def test_run_agent_endpoint_triggers_system_health(staff_client, staff_user):
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=True), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        response = staff_client.post("/api/copilot/agents/system_health/run/")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["status"] == "completed"
    assert response.data["agent_name"] == "system_health"

    run = AgentRun.objects.get(id=response.data["id"])
    assert run.requested_by_id == staff_user.id
    assert run.trigger == "manual"


@pytest.mark.django_db
def test_run_agent_endpoint_404s_for_unknown_agent(staff_client):
    response = staff_client.post("/api/copilot/agents/not_a_real_agent/run/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_run_list_and_detail_endpoints(staff_client):
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=True), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        SystemHealthAgent().run(trigger="manual")

    list_response = staff_client.get("/api/copilot/runs/")
    assert list_response.status_code == status.HTTP_200_OK
    assert len(list_response.data) == 1
    run_id = list_response.data[0]["id"]
    # list view is the lightweight serializer -- no nested tool_calls
    assert "tool_calls" not in list_response.data[0]

    detail_response = staff_client.get(f"/api/copilot/runs/{run_id}/")
    assert detail_response.status_code == status.HTTP_200_OK
    assert len(detail_response.data["tool_calls"]) == 3


@pytest.mark.django_db
def test_recommendation_list_endpoint_filters_by_status(staff_client):
    Recommendation.objects.create(title="A", description="", category="system", status="pending")
    Recommendation.objects.create(title="B", description="", category="system", status="approved")

    response = staff_client.get("/api/copilot/recommendations/?status=pending")

    assert response.status_code == status.HTTP_200_OK
    assert [r["title"] for r in response.data] == ["A"]

@pytest.mark.django_db
def test_recommendation_list_exposes_the_real_action_payload(staff_client, test_user):
    # The approval UI must be able to show the admin what will *actually*
    # execute (tool + arguments), not just the LLM-authored title/description
    # -- those are free text and can be wrong or even mismatched from the
    # real action_payload (e.g. a hallucinated proposal titled "rename user"
    # whose payload is really deactivate_user).
    Recommendation.objects.create(
        title="Rename user test@example.com to test3",
        description="",
        category="users",
        status="pending",
        action_payload={"tool": "deactivate_user", "input": {"user_id": test_user.id}},
    )

    response = staff_client.get("/api/copilot/recommendations/?status=pending")

    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["action_payload"] == {"tool": "deactivate_user", "input": {"user_id": test_user.id}}


@pytest.mark.django_db
def test_dashboard_summary_endpoint(staff_client):
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=False), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        SystemHealthAgent().run(trigger="manual")

    response = staff_client.get("/api/copilot/dashboard-summary/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["runs_today"] == 1
    assert response.data["runs_failed_today"] == 0
    assert response.data["pending_recommendations"] == 1
    assert "system_health" in response.data["agents_registered"]
    assert response.data["llm_configured"] is False


@pytest.mark.django_db
def test_conversation_message_str_and_ordering(test_user):
    older = ConversationMessage.objects.create(user=test_user, role="admin", content="first")
    newer = ConversationMessage.objects.create(user=test_user, role="agent", content="second")
    assert list(ConversationMessage.objects.filter(user=test_user)) == [older, newer]


@pytest.mark.django_db
def test_tool_call_log_str():
    run = AgentRunRepository().start(agent_name="system_health", trigger="manual")
    log = ToolCallLog.objects.create(agent_run=run, tool_name="check_database", success=True)
    assert "check_database" in str(log)


# ---------------------------------------------------------------------------
# Analytics tools + agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_task_stats_tool(task_factory):
    task_factory(status="Completed")
    task_factory(status="Pending")
    result = GetTaskStatsTool().run()
    assert result.success is True
    assert result.data["total"] == 2
    assert result.data["by_status"]["Completed"] == 1
    assert result.data["completion_rate_pct"] == 50.0


@pytest.mark.django_db
def test_get_task_stats_tool_empty():
    result = GetTaskStatsTool().run()
    assert result.data == {"total": 0, "by_status": {}, "completion_rate_pct": 0.0}


@pytest.mark.django_db
def test_get_productivity_trends_tool(task_factory):
    from django.utils import timezone
    t = task_factory(status="Completed")
    t.completed_at = timezone.now()
    t.save(update_fields=["completed_at"])
    result = GetProductivityTrendsTool().run(days=7)
    assert result.success is True
    assert sum(result.data["completions_by_day"].values()) == 1


@pytest.mark.django_db
def test_get_category_breakdown_tool(task_factory, category_factory):
    cat = category_factory(name="Work")
    task_factory(category=cat)
    result = GetCategoryBreakdownTool().run()
    assert result.data["by_category"]["Work"] == 1


@pytest.mark.django_db
def test_analytics_agent_run(task_factory):
    task_factory(status="Completed")
    run = AnalyticsAgent().run(trigger="manual")
    assert run.status == "completed"
    assert "Completion rate" in run.result_summary


@pytest.mark.django_db
def test_analytics_agent_flags_low_completion_rate(task_factory):
    for _ in range(6):
        task_factory(status="Pending")
    task_factory(status="Completed")
    run = AnalyticsAgent().run(trigger="manual")
    assert run.recommendations.count() == 1
    assert run.recommendations.first().category == "tasks"


@pytest.mark.django_db
def test_analytics_agent_no_alert_when_completion_rate_healthy(task_factory):
    task_factory(status="Completed")
    task_factory(status="Completed")
    run = AnalyticsAgent().run(trigger="manual")
    assert run.recommendations.count() == 0


# ---------------------------------------------------------------------------
# User tools + agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list_inactive_users_tool(test_user):
    from django.utils import timezone
    test_user.last_login = timezone.now() - timezone.timedelta(days=100)
    test_user.save(update_fields=["last_login"])
    result = ListInactiveUsersTool().run(days=30)
    assert result.success is True
    emails = [u["email"] for u in result.data["inactive_users"]]
    assert test_user.email in emails


@pytest.mark.django_db
def test_list_inactive_users_tool_excludes_staff(staff_user):
    result = ListInactiveUsersTool().run(days=0)
    emails = [u["email"] for u in result.data["inactive_users"]]
    assert staff_user.email not in emails


@pytest.mark.django_db
def test_get_user_growth_stats_tool(test_user):
    result = GetUserGrowthStatsTool().run(days=14)
    assert result.success is True
    assert sum(result.data["signups_by_day"].values()) >= 1


@pytest.mark.django_db
def test_deactivate_user_tool(test_user):
    result = DeactivateUserTool().run(user_id=test_user.id)
    assert result.success is True
    test_user.refresh_from_db()
    assert test_user.is_active is False


@pytest.mark.django_db
def test_deactivate_user_tool_refuses_superuser(test_user):
    test_user.is_superuser = True
    test_user.save(update_fields=["is_superuser"])
    result = DeactivateUserTool().run(user_id=test_user.id)
    assert result.success is False


@pytest.mark.django_db
def test_deactivate_user_tool_unknown_user():
    result = DeactivateUserTool().run(user_id=999999)
    assert result.success is False


@pytest.mark.django_db
def test_list_all_users_tool_includes_active_and_inactive(test_user):
    test_user.is_active = False
    test_user.save(update_fields=["is_active"])
    result = ListAllUsersTool().run()
    assert result.success is True
    emails = [u["email"] for u in result.data["users"]]
    assert test_user.email in emails


@pytest.mark.django_db
def test_list_all_users_tool_status_filter(test_user, other_user):
    test_user.is_active = False
    test_user.save(update_fields=["is_active"])
    result = ListAllUsersTool().run(status="inactive")
    emails = [u["email"] for u in result.data["users"]]
    assert test_user.email in emails
    assert other_user.email not in emails


@pytest.mark.django_db
def test_list_all_users_tool_keyword_filter(test_user, other_user):
    result = ListAllUsersTool().run(keyword=test_user.email)
    emails = [u["email"] for u in result.data["users"]]
    assert test_user.email in emails
    assert other_user.email not in emails


@pytest.mark.django_db
def test_delete_user_tool(test_user):
    user_id = test_user.id
    result = DeleteUserTool().run(user_id=user_id)
    assert result.success is True
    assert not User.objects.filter(id=user_id).exists()


@pytest.mark.django_db
def test_delete_user_tool_refuses_staff(staff_user):
    result = DeleteUserTool().run(user_id=staff_user.id)
    assert result.success is False
    assert User.objects.filter(id=staff_user.id).exists()


@pytest.mark.django_db
def test_delete_user_tool_refuses_superuser(test_user):
    test_user.is_superuser = True
    test_user.save(update_fields=["is_superuser"])
    result = DeleteUserTool().run(user_id=test_user.id)
    assert result.success is False
    assert User.objects.filter(id=test_user.id).exists()


@pytest.mark.django_db
def test_delete_user_tool_unknown_user():
    result = DeleteUserTool().run(user_id=999999)
    assert result.success is False


@pytest.mark.django_db
def test_rename_user_tool(test_user):
    result = RenameUserTool().run(user_id=test_user.id, new_name="New Name")
    assert result.success is True
    test_user.refresh_from_db()
    assert test_user.first_name == "New Name"


@pytest.mark.django_db
def test_rename_user_tool_rejects_invalid_name(test_user):
    result = RenameUserTool().run(user_id=test_user.id, new_name="123")
    assert result.success is False
    test_user.refresh_from_db()
    assert test_user.first_name != "123"


@pytest.mark.django_db
def test_rename_user_tool_unknown_user():
    result = RenameUserTool().run(user_id=999999, new_name="New Name")
    assert result.success is False


@pytest.mark.django_db
def test_delete_user_and_rename_user_are_sensitive_and_excluded_from_chat_schema():
    assert DeleteUserTool().is_sensitive is True
    assert RenameUserTool().is_sensitive is True
    schema_names = {t["function"]["name"] for t in ChatService()._chat_tools_schema()}
    assert "delete_user" not in schema_names
    assert "rename_user" not in schema_names
    assert "list_all_users" in schema_names


@pytest.mark.django_db
def test_user_monitoring_agent_proposes_deactivation_for_dormant_zero_activity_user(test_user):
    from django.utils import timezone
    test_user.last_login = timezone.now() - timezone.timedelta(days=100)
    test_user.save(update_fields=["last_login"])

    run = UserMonitoringAgent().run(trigger="manual")
    assert run.status == "completed"
    assert run.recommendations.count() == 1
    rec = run.recommendations.first()
    assert rec.requires_approval is True
    assert rec.action_payload == {"tool": "deactivate_user", "input": {"user_id": test_user.id}}


@pytest.mark.django_db
def test_user_monitoring_agent_does_not_duplicate_proposal(test_user):
    from django.utils import timezone
    test_user.last_login = timezone.now() - timezone.timedelta(days=100)
    test_user.save(update_fields=["last_login"])

    UserMonitoringAgent().run(trigger="manual")
    UserMonitoringAgent().run(trigger="manual")

    assert Recommendation.objects.filter(category="users", status="pending").count() == 1


# ---------------------------------------------------------------------------
# Task tools + agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list_overdue_tasks_tool(task_factory):
    from django.utils import timezone
    task_factory(status="Pending", end_time=timezone.now() - timezone.timedelta(hours=1))
    task_factory(status="Completed", end_time=timezone.now() - timezone.timedelta(hours=1))
    result = ListOverdueTasksTool().run()
    assert result.success is True
    assert result.data["total_overdue"] == 1


@pytest.mark.django_db
def test_list_stale_pending_tasks_tool(task_factory):
    from django.utils import timezone
    task_factory(status="Pending", start_time=timezone.now() - timezone.timedelta(hours=48))
    result = ListStalePendingTasksTool().run(hours=24)
    assert result.data["count"] == 1


@pytest.mark.django_db
def test_get_task_completion_by_category_tool(task_factory, category_factory):
    cat = category_factory(name="Work")
    task_factory(category=cat, status="Completed")
    task_factory(category=cat, status="Pending")
    result = GetTaskCompletionByCategoryTool().run()
    assert result.data["by_category"]["Work"]["total"] == 2
    assert result.data["by_category"]["Work"]["completed"] == 1
    assert result.data["by_category"]["Work"]["completion_rate_pct"] == 50.0


@pytest.mark.django_db
def test_task_intelligence_agent_flags_high_overdue_count(task_factory):
    from django.utils import timezone
    for _ in range(11):
        task_factory(status="Pending", end_time=timezone.now() - timezone.timedelta(hours=1))
    run = TaskIntelligenceAgent().run(trigger="manual")
    assert run.status == "completed"
    assert run.recommendations.count() == 1


@pytest.mark.django_db
def test_task_intelligence_agent_no_alert_when_overdue_low(task_factory):
    from django.utils import timezone
    task_factory(status="Pending", end_time=timezone.now() - timezone.timedelta(hours=1))
    run = TaskIntelligenceAgent().run(trigger="manual")
    assert run.recommendations.count() == 0


# ---------------------------------------------------------------------------
# Reminder tools + agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list_reminder_candidates_tool_finds_overdue(task_factory):
    from django.utils import timezone
    task_factory(status="Pending", end_time=timezone.now() - timezone.timedelta(minutes=5), reminder_overdue_sent=False)
    result = ListReminderCandidatesTool().run()
    assert result.success is True
    assert result.data["count"] == 1
    assert result.data["candidates"][0]["kind"] == "overdue"


@pytest.mark.django_db
def test_send_reminder_tool_unknown_type(task_factory):
    task = task_factory()
    result = SendReminderTool().run(task_id=task.id, reminder_type="bogus")
    assert result.success is False


@pytest.mark.django_db
def test_send_reminder_tool_unknown_task():
    result = SendReminderTool().run(task_id=999999, reminder_type="overdue")
    assert result.success is False


@pytest.mark.django_db
def test_send_reminder_tool_calls_underlying_function(task_factory):
    from django.utils import timezone
    task = task_factory(status="Pending", end_time=timezone.now() - timezone.timedelta(minutes=5))

    def fake_send(task_id, version):
        t = Task.objects.get(pk=task_id)
        t.reminder_overdue_sent = True
        t.save(update_fields=["reminder_overdue_sent"])

    with patch("copilot.tools.reminder_tools.send_overdue_reminder", side_effect=fake_send):
        result = SendReminderTool().run(task_id=task.id, reminder_type="overdue")

    assert result.success is True
    assert result.data["sent"] is True


@pytest.mark.django_db
def test_reminder_agent_proposes_action_for_overdue_task(task_factory):
    from django.utils import timezone
    task_factory(status="Pending", end_time=timezone.now() - timezone.timedelta(minutes=5), title="Ship report")
    run = ReminderAgent().run(trigger="manual")
    assert run.status == "completed"
    assert run.recommendations.count() == 1
    rec = run.recommendations.first()
    assert rec.action_payload["tool"] == "send_reminder"


@pytest.mark.django_db
def test_reminder_agent_no_candidates_no_recommendation():
    run = ReminderAgent().run(trigger="manual")
    assert run.status == "completed"
    assert run.recommendations.count() == 0


# ---------------------------------------------------------------------------
# Database tools + agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_database_stats_tool(test_user, task_factory):
    task_factory()
    result = GetDatabaseStatsTool().run()
    assert result.success is True
    assert result.data["users"] >= 1
    assert result.data["tasks"] >= 1


@pytest.mark.django_db
def test_find_duplicate_categories_tool(test_user):
    from categories.models import Category
    Category.objects.create(name="Work", user=test_user)
    Category.objects.create(name="work", user=test_user)
    result = FindDuplicateCategoriesTool().run()
    assert result.data["count"] == 1


@pytest.mark.django_db
def test_find_duplicate_categories_tool_no_duplicates(category_factory):
    category_factory(name="Work")
    result = FindDuplicateCategoriesTool().run()
    assert result.data["count"] == 0


@pytest.mark.django_db
def test_get_copilot_activity_stats_tool():
    AgentRunRepository().start(agent_name="system_health", trigger="manual")
    result = GetCopilotActivityStatsTool().run()
    assert result.data["agent_runs_by_status"]["running"] == 1


@pytest.mark.django_db
def test_database_intelligence_agent_flags_duplicates(test_user):
    from categories.models import Category
    Category.objects.create(name="Work", user=test_user)
    Category.objects.create(name="work", user=test_user)
    run = DatabaseIntelligenceAgent().run(trigger="manual")
    assert run.status == "completed"
    assert run.recommendations.count() == 1
    assert run.recommendations.first().category == "database"


@pytest.mark.django_db
def test_database_intelligence_agent_no_duplicates(category_factory):
    category_factory(name="Work")
    run = DatabaseIntelligenceAgent().run(trigger="manual")
    assert run.recommendations.count() == 0


# ---------------------------------------------------------------------------
# Recommendation (digest) agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_recommendation_agent_no_pending():
    run = RecommendationAgent().run(trigger="manual")
    assert run.status == "completed"
    assert "No pending recommendations" in run.result_summary


@pytest.mark.django_db
def test_recommendation_agent_summarizes_pending_by_risk():
    Recommendation.objects.create(title="Low risk one", description="", category="system", status="pending", risk="low")
    Recommendation.objects.create(title="High risk one", description="", category="system", status="pending", risk="high")
    run = RecommendationAgent().run(trigger="manual")
    assert run.status == "completed"
    assert run.result_summary.index("High risk one") < run.result_summary.index("Low risk one")
    assert Recommendation.objects.filter(status="pending").count() == 2


# ---------------------------------------------------------------------------
# Action agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_action_agent_executes_approved_recommendation(test_user):
    rec = Recommendation.objects.create(
        title="Deactivate dormant account",
        description="",
        category="users",
        status="approved",
        action_payload={"tool": "deactivate_user", "input": {"user_id": test_user.id}},
    )
    run = ActionAgent().run(trigger="manual")
    assert run.status == "completed"
    rec.refresh_from_db()
    assert rec.status == "executed"
    test_user.refresh_from_db()
    assert test_user.is_active is False


@pytest.mark.django_db
def test_action_agent_marks_failed_when_tool_fails():
    rec = Recommendation.objects.create(
        title="Deactivate a user that doesn't exist",
        description="",
        category="users",
        status="approved",
        action_payload={"tool": "deactivate_user", "input": {"user_id": 999999}},
    )
    run = ActionAgent().run(trigger="manual")
    assert run.status == "completed"  # the agent itself ran fine; the underlying action failed
    rec.refresh_from_db()
    assert rec.status == "failed"
    assert "error" in rec.execution_result


@pytest.mark.django_db
def test_action_agent_ignores_pending_and_rejected():
    Recommendation.objects.create(title="Pending one", description="", category="users", status="pending")
    Recommendation.objects.create(title="Rejected one", description="", category="users", status="rejected")
    run = ActionAgent().run(trigger="manual")
    assert run.status == "completed"
    assert run.tool_calls.count() == 0


@pytest.mark.django_db
def test_action_agent_scoped_to_only_ids(test_user, other_user):
    rec1 = Recommendation.objects.create(
        title="Deactivate user 1", description="", category="users", status="approved",
        action_payload={"tool": "deactivate_user", "input": {"user_id": test_user.id}},
    )
    rec2 = Recommendation.objects.create(
        title="Deactivate user 2", description="", category="users", status="approved",
        action_payload={"tool": "deactivate_user", "input": {"user_id": other_user.id}},
    )
    ActionAgent(only_ids=[rec1.id]).run(trigger="manual")
    rec1.refresh_from_db()
    rec2.refresh_from_db()
    assert rec1.status == "executed"
    assert rec2.status == "approved"  # untouched


# ---------------------------------------------------------------------------
# RecommendationRepository additions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_recommendation_repository_approve_and_reject(staff_user):
    repo = RecommendationRepository()
    rec = repo.create(title="A", description="", category="system", status="pending")
    approved = repo.approve(rec, by_user=staff_user)
    assert approved.status == "approved"
    assert approved.resolved_by_id == staff_user.id
    assert approved.resolved_at is not None

    rec2 = repo.create(title="B", description="", category="system", status="pending")
    rejected = repo.reject(rec2, by_user=staff_user)
    assert rejected.status == "rejected"


@pytest.mark.django_db
def test_recommendation_repository_mark_executed_and_failed():
    repo = RecommendationRepository()
    rec = repo.create(title="A", description="", category="system", status="approved")
    executed = repo.mark_executed(rec, result={"ok": True})
    assert executed.status == "executed"
    assert executed.execution_result == {"ok": True}

    rec2 = repo.create(title="B", description="", category="system", status="approved")
    failed = repo.mark_failed(rec2, error="boom")
    assert failed.status == "failed"
    assert failed.execution_result == {"error": "boom"}


@pytest.mark.django_db
def test_recommendation_repository_approved_pending_filters_by_ids():
    repo = RecommendationRepository()
    rec1 = repo.create(title="A", description="", category="system", status="approved")
    repo.create(title="B", description="", category="system", status="approved")
    assert [r.id for r in repo.approved_pending(ids=[rec1.id])] == [rec1.id]


@pytest.mark.django_db
def test_recommendation_repository_has_pending_action():
    repo = RecommendationRepository()
    repo.create(
        title="A", description="", category="users", status="pending",
        action_payload={"tool": "deactivate_user", "input": {"user_id": 5}},
    )
    assert repo.has_pending_action(tool="deactivate_user", input_match={"user_id": 5}) is True
    assert repo.has_pending_action(tool="deactivate_user", input_match={"user_id": 6}) is False


@pytest.mark.django_db
def test_recommendation_repository_has_recent_pending():
    repo = RecommendationRepository()
    repo.create(title="Dup alert", description="", category="database", status="pending")
    assert repo.has_recent_pending(title="Dup alert", category="database") is True
    assert repo.has_recent_pending(title="Other alert", category="database") is False


# ---------------------------------------------------------------------------
# propose_action tool
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_propose_action_tool_creates_pending_recommendation():
    result = ProposeActionTool().run(
        title="Deactivate a stale user",
        description="Hasn't logged in for 200 days.",
        tool="deactivate_user",
        tool_input={"user_id": 42},
        category="users",
        risk="high",
    )
    assert result.success is True
    rec = Recommendation.objects.get(id=result.data["recommendation_id"])
    assert rec.status == "pending"
    assert rec.action_payload == {"tool": "deactivate_user", "input": {"user_id": 42}}
    assert rec.risk == "high"


@pytest.mark.django_db
def test_propose_action_tool_rejects_unknown_tool():
    result = ProposeActionTool().run(
        title="Do something weird", description="", tool="not_a_real_tool", tool_input={}, category="system",
    )
    assert result.success is False
    assert Recommendation.objects.count() == 0


@pytest.mark.django_db
def test_propose_action_tool_requires_title_and_tool():
    result = ProposeActionTool().run(title="", description="", tool="", tool_input={}, category="system")
    assert result.success is False


# ---------------------------------------------------------------------------
# ChatService
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_chat_service_not_configured_raises(test_user):
    service = ChatService(llm=GroqClient(api_key=""))
    with pytest.raises(ChatNotConfiguredError):
        service.send(user=test_user, message="hi")


@pytest.mark.django_db
def test_chat_service_plain_reply_no_tool_call(test_user):
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response("You have 3 tasks overdue.")
        ))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = ChatService(llm=llm).send(user=test_user, message="how many tasks are overdue?")

    assert result["reply"] == "You have 3 tasks overdue."
    assert result["tool_calls"] == []
    history = MemoryService().recent_history(user=test_user)
    assert [m.role for m in history] == ["admin", "agent"]


@pytest.mark.django_db
def test_chat_service_calls_a_read_only_tool_then_replies(test_user, task_factory):
    task_factory(status="Completed")
    call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="get_task_stats", arguments="{}"))
    responses = [
        _fake_groq_response(content="", tool_calls=[call]),
        _fake_groq_response(content="You're at 100% completion."),
    ]
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: responses.pop(0)))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = ChatService(llm=llm).send(user=test_user, message="what's our completion rate?")

    assert result["reply"] == "You're at 100% completion."
    assert result["tool_calls"][0]["tool"] == "get_task_stats"
    assert result["tool_calls"][0]["output"]["success"] is True


@pytest.mark.django_db
def test_chat_service_refuses_sensitive_tool_even_if_requested(test_user):
    call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="deactivate_user", arguments='{"user_id": 1}'))
    responses = [
        _fake_groq_response(content="", tool_calls=[call]),
        _fake_groq_response(content="I can't do that directly."),
    ]
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: responses.pop(0)))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = ChatService(llm=llm).send(user=test_user, message="deactivate user 1")

    assert result["tool_calls"][0]["output"]["success"] is False
    assert "not available" in result["tool_calls"][0]["output"]["error"]


@pytest.mark.django_db
def test_chat_service_propose_action_executes_immediately_for_the_admin_chatting(test_user, other_user):
    # Chat's propose_action runs on behalf of whichever admin is chatting
    # (this endpoint is IsAdminUser-gated), so it executes right away rather
    # than sitting as a pending recommendation for someone else to approve.
    call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(
            name="propose_action",
            arguments=(
                '{"title": "Deactivate stale user", "description": "d", "tool": "deactivate_user", '
                f'"tool_input": {{"user_id": {other_user.id}}}, "category": "users", "risk": "medium"}}'
            ),
        ),
    )
    responses = [
        _fake_groq_response(content="", tool_calls=[call]),
        _fake_groq_response(content="Done -- I've deactivated that account."),
    ]
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: responses.pop(0)))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = ChatService(llm=llm).send(user=test_user, message="deactivate that user, they're stale")

    assert result["proposed_recommendation"] is not None
    rec = Recommendation.objects.get(id=result["proposed_recommendation"]["recommendation_id"])
    assert rec.status == "executed"
    assert rec.resolved_by == test_user
    assert rec.action_payload == {"tool": "deactivate_user", "input": {"user_id": other_user.id}}
    other_user.refresh_from_db()
    assert other_user.is_active is False


@pytest.mark.django_db
def test_chat_service_propose_action_reports_execution_failure(test_user):
    call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(
            name="propose_action",
            arguments=(
                '{"title": "Deactivate unknown user", "description": "d", "tool": "deactivate_user", '
                '"tool_input": {"user_id": 999999}, "category": "users", "risk": "medium"}'
            ),
        ),
    )
    responses = [
        _fake_groq_response(content="", tool_calls=[call]),
        _fake_groq_response(content="That failed -- no such user."),
    ]
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: responses.pop(0)))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = ChatService(llm=llm).send(user=test_user, message="deactivate user 999999")

    rec = Recommendation.objects.get(id=result["proposed_recommendation"]["recommendation_id"])
    assert rec.status == "failed"
    assert result["tool_calls"][0]["output"]["success"] is False


@pytest.mark.django_db
def test_chat_service_exhausts_rounds_falls_back(test_user):
    call = SimpleNamespace(id="call_1", function=SimpleNamespace(name="get_task_stats", arguments="{}"))
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response(content="", tool_calls=[call])
        ))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = ChatService(llm=llm).send(user=test_user, message="loop forever")

    assert "try rephrasing" in result["reply"]


# ---------------------------------------------------------------------------
# New agent endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_agent_status_lists_all_eight_agents(staff_client):
    response = staff_client.get("/api/copilot/agent-status/")
    names = {row["name"] for row in response.data}
    assert names == {
        "system_health", "analytics", "user_monitoring", "task_intelligence",
        "reminder", "database_intelligence", "recommendation", "action",
    }


@pytest.mark.django_db
def test_run_agent_endpoint_triggers_analytics(staff_client):
    response = staff_client.post("/api/copilot/agents/analytics/run/")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["agent_name"] == "analytics"


# ---------------------------------------------------------------------------
# Approve / reject endpoints
# ---------------------------------------------------------------------------

APPROVAL_ENDPOINTS = [
    ("post", "/api/copilot/recommendations/1/approve/"),
    ("post", "/api/copilot/recommendations/1/reject/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", APPROVAL_ENDPOINTS)
def test_approval_endpoints_reject_unauthenticated(api_client, method, url):
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", APPROVAL_ENDPOINTS)
def test_approval_endpoints_reject_non_staff(auth_client, method, url):
    response = getattr(auth_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_approve_recommendation_endpoint_executes_action(staff_client, test_user):
    rec = Recommendation.objects.create(
        title="Deactivate dormant account", description="", category="users", status="pending",
        action_payload={"tool": "deactivate_user", "input": {"user_id": test_user.id}},
    )
    response = staff_client.post(f"/api/copilot/recommendations/{rec.id}/approve/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "executed"
    test_user.refresh_from_db()
    assert test_user.is_active is False


@pytest.mark.django_db
def test_approve_recommendation_endpoint_observation_only_just_marks_approved(staff_client):
    rec = Recommendation.objects.create(title="Alert", description="", category="system", status="pending")
    response = staff_client.post(f"/api/copilot/recommendations/{rec.id}/approve/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "approved"  # nothing to execute


@pytest.mark.django_db
def test_approve_recommendation_endpoint_rejects_already_resolved(staff_client):
    rec = Recommendation.objects.create(title="Alert", description="", category="system", status="executed")
    response = staff_client.post(f"/api/copilot/recommendations/{rec.id}/approve/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_reject_recommendation_endpoint(staff_client, staff_user):
    rec = Recommendation.objects.create(title="Alert", description="", category="system", status="pending")
    response = staff_client.post(f"/api/copilot/recommendations/{rec.id}/reject/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "rejected"
    rec.refresh_from_db()
    assert rec.resolved_by_id == staff_user.id


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------

CHAT_ENDPOINTS = [
    ("post", "/api/copilot/chat/send/"),
    ("get", "/api/copilot/chat/history/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", CHAT_ENDPOINTS)
def test_chat_endpoints_reject_unauthenticated(api_client, method, url):
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("method, url", CHAT_ENDPOINTS)
def test_chat_endpoints_reject_non_staff(auth_client, method, url):
    response = getattr(auth_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_chat_send_endpoint_without_key_returns_503(staff_client, settings):
    settings.GROQ_API_KEY = ""
    response = staff_client.post("/api/copilot/chat/send/", {"message": "hello"}, format="json")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.django_db
def test_chat_send_endpoint_rejects_empty_message(staff_client):
    response = staff_client.post("/api/copilot/chat/send/", {"message": "   "}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_chat_send_endpoint_success(staff_client, settings):
    settings.GROQ_API_KEY = "fake-key"
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: _fake_groq_response("Hi, how can I help?")
        ))
    )
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        response = staff_client.post("/api/copilot/chat/send/", {"message": "hello"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["reply"] == "Hi, how can I help?"


@pytest.mark.django_db
def test_delete_completed_tasks_tool(task_factory):
    from django.utils import timezone
    old = task_factory(status="Completed")
    old.completed_at = timezone.now() - timezone.timedelta(days=40)
    old.save(update_fields=["completed_at"])
    recent = task_factory(status="Completed")
    recent.completed_at = timezone.now() - timezone.timedelta(days=5)
    recent.save(update_fields=["completed_at"])

    result = DeleteCompletedTasksTool().run(older_than_days=30)
    assert result.success is True
    assert result.data["deleted_count"] == 1
    assert result.data["deleted_task_ids"] == [old.id]
    assert Task.objects.filter(id=old.id).exists() is False
    assert Task.objects.filter(id=recent.id).exists() is True


@pytest.mark.django_db
def test_delete_completed_tasks_tool_no_matches():
    result = DeleteCompletedTasksTool().run(older_than_days=30)
    assert result.success is True
    assert result.data["deleted_count"] == 0


@pytest.mark.django_db
def test_base_agent_continues_plan_after_one_tool_raises():
    class FlakyAgent(SystemHealthAgent):
        def plan(self, observation, reasoning):
            return [PlannedStep(tool_name="check_redis"), PlannedStep(tool_name="check_database")]

    with patch("copilot.tools.system_tools.check_redis", side_effect=ConnectionError("simulated outage")), \
         patch("copilot.tools.system_tools.check_database", return_value=True):
        run = FlakyAgent().run(trigger="manual")

    # The whole run still completes (not "failed") even though one tool
    # blew up mid-plan -- the other step still executed and got logged.
    assert run.status == "completed"
    assert run.tool_calls.count() == 2
    redis_log = run.tool_calls.get(tool_name="check_redis")
    assert redis_log.success is False
    assert "simulated outage" in redis_log.error
    db_log = run.tool_calls.get(tool_name="check_database")
    assert db_log.success is True


@pytest.mark.django_db
def test_system_health_agent_does_not_duplicate_alert_across_runs():
    with patch("copilot.tools.system_tools.check_database", return_value=True), \
         patch("copilot.tools.system_tools.check_redis", return_value=False), \
         patch("copilot.tools.system_tools.check_celery_workers", return_value=["worker1"]):
        SystemHealthAgent().run(trigger="manual")
        SystemHealthAgent().run(trigger="manual")

    assert Recommendation.objects.filter(category="system", status="pending").count() == 1


@pytest.mark.django_db
def test_chat_service_run_tool_catches_tool_exception(test_user):
    with patch("copilot.tools.analytics_tools.GetTaskStatsTool.run", side_effect=RuntimeError("db is down")):
        service = ChatService(llm=GroqClient(api_key="fake-key"))
        output = service._run_tool("get_task_stats", {}, user=test_user)

    assert output["success"] is False
    assert "db is down" in output["error"]


@pytest.mark.django_db
def test_chat_service_llm_outage_returns_graceful_reply_not_exception(test_user):
    fake_inner_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("groq is unreachable"))
        ))
    )
    llm = GroqClient(api_key="fake-key")
    with patch.object(GroqClient, "_get_client", return_value=fake_inner_client):
        result = ChatService(llm=llm).send(user=test_user, message="hello")  # must not raise

    assert "trouble reaching" in result["reply"]


@pytest.mark.django_db
def test_chat_service_system_prompt_lists_sensitive_tool_names():
    prompt = ChatService()._system_prompt()
    assert "deactivate_user" in prompt
    assert "send_reminder" in prompt
    assert "delete_completed_tasks" in prompt


@pytest.mark.django_db
def test_chat_history_endpoint(staff_client, staff_user):
    MemoryService().add_message(user=staff_user, content="hi", role="admin")
    MemoryService().add_message(user=staff_user, content="hello", role="agent")
    response = staff_client.get("/api/copilot/chat/history/")
    assert response.status_code == status.HTTP_200_OK
    assert [m["content"] for m in response.data] == ["hi", "hello"]
