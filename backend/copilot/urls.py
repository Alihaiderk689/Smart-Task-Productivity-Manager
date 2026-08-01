from django.urls import path

from . import views

urlpatterns = [
    path("agent-status/", views.agent_status, name="copilot-agent-status"),
    path("agents/<str:agent_name>/run/", views.run_agent, name="copilot-run-agent"),
    path("runs/", views.AgentRunListView.as_view(), name="copilot-run-list"),
    path("runs/<int:pk>/", views.AgentRunDetailView.as_view(), name="copilot-run-detail"),
    path("recommendations/", views.RecommendationListView.as_view(), name="copilot-recommendation-list"),
    path("recommendations/<int:pk>/approve/", views.approve_recommendation, name="copilot-recommendation-approve"),
    path("recommendations/<int:pk>/reject/", views.reject_recommendation, name="copilot-recommendation-reject"),
    path("dashboard-summary/", views.dashboard_summary, name="copilot-dashboard-summary"),
    path("chat/send/", views.chat_send, name="copilot-chat-send"),
    path("chat/history/", views.chat_history, name="copilot-chat-history"),
]
