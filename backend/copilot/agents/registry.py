"""Maps agent name -> agent class. Only agents that actually exist are
registered here -- the /agent-status/ endpoint reports exactly this list,
so it never claims an agent exists that hasn't been built yet."""

from __future__ import annotations

from .action import ActionAgent
from .analytics import AnalyticsAgent
from .database_intelligence import DatabaseIntelligenceAgent
from .recommendation import RecommendationAgent
from .reminder import ReminderAgent
from .system_health import SystemHealthAgent
from .task_intelligence import TaskIntelligenceAgent
from .user_monitoring import UserMonitoringAgent

AGENT_REGISTRY: dict[str, type] = {
    SystemHealthAgent.name: SystemHealthAgent,
    AnalyticsAgent.name: AnalyticsAgent,
    UserMonitoringAgent.name: UserMonitoringAgent,
    TaskIntelligenceAgent.name: TaskIntelligenceAgent,
    ReminderAgent.name: ReminderAgent,
    DatabaseIntelligenceAgent.name: DatabaseIntelligenceAgent,
    RecommendationAgent.name: RecommendationAgent,
    ActionAgent.name: ActionAgent,
}


def get_agent_class(name: str):
    return AGENT_REGISTRY.get(name)
