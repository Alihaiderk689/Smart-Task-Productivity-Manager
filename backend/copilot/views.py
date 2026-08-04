from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response

from .agents.registry import AGENT_REGISTRY, get_agent_class
from .llm.fallback_client import LLMClient
from .memory.service import MemoryService
from .models import AgentRun, Recommendation
from .permissions import IsAdminUser
from .repositories import AgentRunRepository, RecommendationRepository
from .serializers import (
    AgentRunListSerializer,
    AgentRunSerializer,
    ChatRequestSerializer,
    ConversationMessageSerializer,
    RecommendationSerializer,
)
from .services.chat_service import ChatNotConfiguredError, ChatService


@api_view(["GET"])
@permission_classes([IsAdminUser])
def agent_status(request):
    """Every registered agent, with its most recent run (if any) -- powers
    the "Agent Status" / "System Health" section of the copilot dashboard."""
    repo = AgentRunRepository()
    data = []
    for name, agent_cls in AGENT_REGISTRY.items():
        last_run = repo.last_for(name)
        data.append({
            "name": name,
            "description": agent_cls.description,
            "last_run": AgentRunListSerializer(last_run).data if last_run else None,
        })
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def run_agent(request, agent_name):
    """Manually trigger a named agent right now (trigger="manual",
    requested_by=the calling admin) -- the "Run Now" button."""
    agent_cls = get_agent_class(agent_name)
    if agent_cls is None:
        return Response(
            {"error": f"Unknown agent {agent_name!r}. Known agents: {', '.join(AGENT_REGISTRY)}."},
            status=status.HTTP_404_NOT_FOUND,
        )

    agent = agent_cls()
    run = agent.run(trigger="manual", requested_by=request.user)
    response_status = status.HTTP_201_CREATED if run.status == "completed" else status.HTTP_502_BAD_GATEWAY
    return Response(AgentRunSerializer(run).data, status=response_status)


class AgentRunListView(ListAPIView):
    """Recent agent runs across every agent -- the "Recent Actions" /
    timeline feed. Supports ?agent_name=<name> to filter to one agent."""
    serializer_class = AgentRunListSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = AgentRun.objects.all()
        agent_name = self.request.query_params.get("agent_name")
        if agent_name:
            qs = qs.filter(agent_name=agent_name)
        return qs[:50]


class AgentRunDetailView(RetrieveAPIView):
    """One run's full detail, including every tool call it made -- the
    "thought process" drill-down."""
    serializer_class = AgentRunSerializer
    permission_classes = [IsAdminUser]
    queryset = AgentRun.objects.all()


class RecommendationListView(ListAPIView):
    """AI recommendations/alerts -- supports ?status=pending (etc.) to
    filter, matching the model's STATUS_CHOICES."""
    serializer_class = RecommendationSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = Recommendation.objects.all()
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs[:50]


@api_view(["GET"])
@permission_classes([IsAdminUser])
def dashboard_summary(request):
    """The condensed "Today's Summary" widget: how much the copilot has
    done today and what's waiting on the admin."""
    today = timezone.localdate()
    runs_today = AgentRun.objects.filter(started_at__date=today)

    return Response({
        "runs_today": runs_today.count(),
        "runs_failed_today": runs_today.filter(status="failed").count(),
        "pending_recommendations": Recommendation.objects.filter(status="pending").count(),
        "agents_registered": list(AGENT_REGISTRY.keys()),
        "llm_configured": LLMClient().is_configured,
    })


@api_view(["POST"])
@permission_classes([IsAdminUser])
def approve_recommendation(request, pk):
    """Approves a pending recommendation. If it has an action_payload, this
    also immediately runs ActionAgent scoped to just this one recommendation
    -- an admin approving something expects it to happen right away, not on
    the next scheduled sweep. Observation-only alerts (no action_payload)
    have nothing to execute; approving one just acknowledges it."""
    rec = get_object_or_404(Recommendation, pk=pk)
    if rec.status != "pending":
        return Response({"error": f"Recommendation is already {rec.status}."}, status=status.HTTP_400_BAD_REQUEST)

    repo = RecommendationRepository()
    repo.approve(rec, by_user=request.user)

    if rec.requires_approval:
        from .agents.action import ActionAgent

        ActionAgent(recommendations=repo, only_ids=[rec.id]).run(trigger="manual", requested_by=request.user)
        rec.refresh_from_db()

    return Response(RecommendationSerializer(rec).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def reject_recommendation(request, pk):
    """Rejects (or, for an observation-only alert, dismisses) a pending
    recommendation -- nothing is executed either way."""
    rec = get_object_or_404(Recommendation, pk=pk)
    if rec.status != "pending":
        return Response({"error": f"Recommendation is already {rec.status}."}, status=status.HTTP_400_BAD_REQUEST)

    RecommendationRepository().reject(rec, by_user=request.user)
    rec.refresh_from_db()
    return Response(RecommendationSerializer(rec).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def chat_send(request):
    """Send a free-form message to the copilot chat -- see
    services/chat_service.py for the LLM tool-calling orchestration.
    Requires GROQ_API_KEY; the frontend should keep the chat input disabled
    (with an explanatory note) when dashboard-summary's llm_configured is
    false, same as the "Run Now" no-key banner."""
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        result = ChatService().send(
            user=request.user,
            message=serializer.validated_data["message"],
            session_id=serializer.validated_data["session_id"],
        )
    except ChatNotConfiguredError:
        return Response(
            {"error": "GROQ_API_KEY is not configured -- chat requires an LLM."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(result)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def chat_history(request):
    """This admin's chat history for one session (default 'default'),
    oldest first -- powers the chat panel on load."""
    session_id = request.query_params.get("session_id", "default")
    messages = MemoryService().recent_history(user=request.user, session_id=session_id, limit=50)
    return Response(ConversationMessageSerializer(messages, many=True).data)
