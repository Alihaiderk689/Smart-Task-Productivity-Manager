from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .serializers import ChatRequestSerializer
from .services.chat_service import ChatNotConfiguredError, UserChatService

logger = logging.getLogger(__name__)

_NOT_CONFIGURED_DETAIL = "The AI Copilot isn't configured yet -- ask an admin to set GROQ_API_KEY."


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_send(request):
    """Any authenticated user (staff or not) can use their own copilot --
    in contrast to copilot.views, which is admin-only throughout. Every
    tool this runs is bound to request.user; see tools/registry.py."""
    serializer = ChatRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    service = UserChatService()
    if not service.is_configured:
        return Response({"detail": _NOT_CONFIGURED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        result = service.send(
            user=request.user,
            message=serializer.validated_data["message"],
            history=serializer.validated_data.get("history", []),
        )
    except ChatNotConfiguredError:
        return Response({"detail": _NOT_CONFIGURED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception:
        # Never leak an internal exception/stack trace to the client.
        logger.exception("User copilot chat failed unexpectedly for user %s", request.user.id)
        return Response({"detail": "Something went wrong -- please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(result, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    return Response({"llm_configured": UserChatService().is_configured})
