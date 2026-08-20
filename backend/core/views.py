import hmac
import logging
import time

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .system_checks import check_database
from .throttling import HealthRateThrottle, InternalTaskRateThrottle

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([HealthRateThrottle])
def health(request):
    """Lightweight liveness/readiness probe -- public on purpose (unlike
    run-scheduled-tasks below, there's nothing sensitive here to protect),
    so the scheduled-tasks workflow can poll it to wake a sleeping Render
    free-tier instance and wait for it to actually be ready, without paying
    the cost of a real scheduled-task run just to check reachability. Only
    checks the database (the one dependency actually worth confirming
    before running scheduled jobs) -- deliberately skips the heavier
    Redis/Celery-worker checks in system_checks.get_system_status(), which
    would just add latency and always report "down" in this brokerless
    deployment (see .env.render)."""
    db_ok = check_database()
    return Response({"status": "ok" if db_ok else "error", "database": db_ok}, status=200 if db_ok else 503)


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


def _reminder_jobs():
    # Deliberately its own job group, on its own faster cadence (see
    # .github/workflows/scheduled-tasks.yml), rather than folded into
    # _frequent_jobs above -- the app's 5-minutes-before reminder can't be
    # served reliably by a 15-minute sweep, and this job is pure DB
    # queries + SMTP (no LLM calls like the jobs above), so it stays cheap
    # and fast enough to run that often on its own.
    from notifications.reminder_processor import process_due_reminders

    return {"process_due_reminders": process_due_reminders}


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
    "reminders": _reminder_jobs,
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

    jobs = jobs_factory()
    results = {}
    duration_ms = {}
    for name, task_fn in jobs.items():
        started = time.monotonic()
        try:
            task_fn()
            results[name] = "ok"
        except Exception:
            # Isolated per task on purpose -- one job (e.g. a flaky email
            # send) failing must never stop the rest of the group from
            # running; each task is independent and safe to keep going.
            logger.exception("Scheduled task %r in group %r failed", name, group)
            results[name] = "error"
        duration_ms[name] = int((time.monotonic() - started) * 1000)

    failed = [name for name, outcome in results.items() if outcome == "error"]
    all_ok = not failed
    all_failed = bool(failed) and len(failed) == len(results)

    if all_ok:
        status_code = 200
    elif all_failed:
        # Every job in the group errored -- almost certainly something
        # systemic (DB down, bad deploy) rather than one flaky task, so
        # this is a hard failure worth alerting on distinctly from a
        # partial one.
        status_code = 500
    else:
        # Mixed outcome: the request itself succeeded and most jobs ran
        # fine, but not all of them -- 207 Multi-Status is the honest
        # code for "processed, not uniformly successful". The workflow
        # checks the `success` field in the body rather than relying on
        # curl's --fail (which treats any 2xx, 207 included, as success),
        # so this is still surfaced as a failed CI step.
        status_code = 207

    logger.info(
        "Scheduled tasks group=%r results=%s duration_ms=%s", group, results, duration_ms,
    )

    return Response(
        {"group": group, "success": all_ok, "results": results, "duration_ms": duration_ms},
        status=status_code,
    )
