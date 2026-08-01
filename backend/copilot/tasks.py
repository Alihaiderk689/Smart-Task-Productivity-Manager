"""Celery tasks for the Admin Copilot -- one periodic sweep per agent (see
config/celery.py's beat_schedule for cadence), plus the action-agent sweep
that catches anything approved but not yet executed."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _run_scheduled(agent_cls):
    agent = agent_cls()
    run = agent.run(trigger="scheduled")
    if run.status == "failed":
        logger.error("Scheduled %s check failed: %s", agent_cls.name, run.error)
    return {"agent_run_id": run.id, "status": run.status}


@shared_task
def run_system_health_check():
    from .agents.system_health import SystemHealthAgent

    return _run_scheduled(SystemHealthAgent)


@shared_task
def run_analytics_check():
    from .agents.analytics import AnalyticsAgent

    return _run_scheduled(AnalyticsAgent)


@shared_task
def run_user_monitoring_check():
    from .agents.user_monitoring import UserMonitoringAgent

    return _run_scheduled(UserMonitoringAgent)


@shared_task
def run_task_intelligence_check():
    from .agents.task_intelligence import TaskIntelligenceAgent

    return _run_scheduled(TaskIntelligenceAgent)


@shared_task
def run_reminder_check():
    from .agents.reminder import ReminderAgent

    return _run_scheduled(ReminderAgent)


@shared_task
def run_database_intelligence_check():
    from .agents.database_intelligence import DatabaseIntelligenceAgent

    return _run_scheduled(DatabaseIntelligenceAgent)


@shared_task
def run_recommendation_digest():
    from .agents.recommendation import RecommendationAgent

    return _run_scheduled(RecommendationAgent)


@shared_task
def run_action_agent_sweep():
    """Executes any recommendation left in status='approved' -- normally
    none, since approving one in the UI executes it immediately (see
    views.approve_recommendation), but this is the safety net for anything
    approved through a path that didn't trigger execution."""
    from .agents.action import ActionAgent

    return _run_scheduled(ActionAgent)
