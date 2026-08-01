from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import EvaluationRun
from .runner import run_full_evaluation
from .serializers import EvaluationRunDetailSerializer, EvaluationRunListSerializer


@api_view(["POST"])
@permission_classes([IsAdminUser])
def trigger_evaluation(request):
    """Runs the full evaluation suite synchronously (real Groq calls +
    real DB, ~20 scenarios) and returns the finished run with its metrics.
    Takes a while (tens of seconds) -- the frontend should show a running
    state, same as it does for a single "Run Now" agent call."""
    run = run_full_evaluation(triggered_by=request.user)
    return Response(EvaluationRunDetailSerializer(run).data)


class EvaluationRunListView(ListAPIView):
    """Run history -- powers the trend chart and the run-picker list."""
    serializer_class = EvaluationRunListSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return EvaluationRun.objects.all()[:50]


class EvaluationRunDetailView(RetrieveAPIView):
    """One run's full detail, including every case result -- the "detailed
    logs" drill-down."""
    serializer_class = EvaluationRunDetailSerializer
    permission_classes = [IsAdminUser]
    queryset = EvaluationRun.objects.all()


@api_view(["GET"])
@permission_classes([IsAdminUser])
def latest_summary(request):
    """The most recent run's metrics, plus a short trend of task success
    rate across the last 10 runs -- powers the dashboard's top cards and
    trend line without the client needing to fetch full run history."""
    latest = EvaluationRun.objects.exclude(status="running").first()
    trend = list(
        EvaluationRun.objects.exclude(status="running").order_by("-started_at")[:10]
        .values("id", "started_at", "metrics")
    )
    trend.reverse()

    return Response({
        "latest": EvaluationRunListSerializer(latest).data if latest else None,
        "trend": [
            {"id": t["id"], "started_at": t["started_at"], "task_success_rate": (t["metrics"] or {}).get("task_success_rate")}
            for t in trend
        ],
    })
