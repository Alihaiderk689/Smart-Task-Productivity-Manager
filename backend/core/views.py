import hmac
import logging

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .throttling import InternalTaskRateThrottle

logger = logging.getLogger(__name__)

# Free-tier substitute for Celery Beat: config/celery.py's beat_schedule is
# the source of truth this mirrors, but the deployed environment has no
# `celery beat`/`celery worker`/Redis (see .github/workflows/scheduled-tasks.yml,
# a GitHub Actions cron that calls this endpoint instead). Each task function
# is called directly rather than via .delay()/.apply_async(), which runs it
# synchronously in-process -- normal Celery behavior when there's no broker.


def _frequent_jobs():
    from copilot.tasks import run_action_agent_sweep, run_reminder_check, run_system_health_check

    return {
        "system_health_check": run_system_health_check,
        "reminder_check": run_reminder_check,
        "action_agent_sweep": run_action_agent_sweep,
    }


def _daily_jobs():
    from copilot.tasks import (
        run_analytics_check,
        run_database_intelligence_check,
        run_recommendation_digest,
        run_task_intelligence_check,
        run_user_monitoring_check,
    )
    from notifications.tasks import send_daily_progress_reminders

    return {
        "daily_progress_reminders": send_daily_progress_reminders,
        "analytics_check": run_analytics_check,
        "user_monitoring_check": run_user_monitoring_check,
        "task_intelligence_check": run_task_intelligence_check,
        "database_intelligence_check": run_database_intelligence_check,
        "recommendation_digest": run_recommendation_digest,
    }


JOB_GROUPS = {
    "frequent": _frequent_jobs,
    "daily": _daily_jobs,
}


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([InternalTaskRateThrottle])
def run_scheduled_tasks(request):
    """Not part of the public API surface -- authenticated by a shared
    secret (INTERNAL_TASK_KEY) instead of a user JWT, since the only caller
    is the scheduled-tasks GitHub Actions workflow. Any auth failure returns
    404 rather than 401/403 so the endpoint's existence isn't revealed to
    unauthenticated scanners.
    """
    supplied_key = request.headers.get("X-Internal-Task-Key", "")
    expected_key = settings.INTERNAL_TASK_KEY

    if not expected_key or not hmac.compare_digest(supplied_key, expected_key):
        logger.warning("Rejected scheduled-tasks request: invalid or missing key")
        return Response(status=404)

    group = request.query_params.get("group")
    jobs_factory = JOB_GROUPS.get(group)
    if jobs_factory is None:
        return Response({"error": "unknown or missing 'group' param"}, status=400)

    results = {}
    for name, task_fn in jobs_factory().items():
        try:
            task_fn()
            results[name] = "ok"
        except Exception:
            logger.exception("Scheduled task %s failed", name)
            results[name] = "error"

    return Response({"group": group, "results": results})
