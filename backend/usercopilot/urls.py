from django.urls import path

from . import views

urlpatterns = [
    path("chat/send/", views.chat_send, name="usercopilot-chat-send"),
    path("status/", views.status_view, name="usercopilot-status"),
]
