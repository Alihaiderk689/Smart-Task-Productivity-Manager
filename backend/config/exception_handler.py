import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Wraps DRF's default exception handler. DRF's default already returns
    clean responses for the errors it recognizes (ValidationError, auth
    failures, permission denials, throttling, 404s). This only handles what
    it *doesn't* recognize -- a genuinely unexpected exception (a bug) --
    which would otherwise reach the client as a bare 500 with no JSON body
    (or, in DEBUG, Django's full HTML traceback page). Logs full context so
    it's still debuggable from the server side.
    """
    response = drf_exception_handler(exc, context)

    if response is not None:
        return response

    request = context.get("request")
    view = context.get("view")
    logger.exception(
        "Unhandled exception in %s (%s %s)",
        view.__class__.__name__ if view else "unknown view",
        getattr(request, "method", "?"),
        getattr(request, "path", "?"),
        exc_info=exc,
    )

    return Response(
        {"detail": "An unexpected error occurred. Please try again."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
