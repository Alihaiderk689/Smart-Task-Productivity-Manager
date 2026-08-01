"""Infrastructure health checks shared by adminpanel's /system-status/
endpoint and the copilot app's SystemHealthAgent -- kept in `core` since
neither app owns this concern more than the other.

Each check is deliberately defensive (broad except Exception): a health
checker that itself raises would defeat the point of a health checker.
"""

from django.conf import settings
from django.contrib.auth.models import User


def check_database() -> bool:
    try:
        User.objects.exists()
        return True
    except Exception:
        return False


def check_redis() -> bool:
    try:
        import redis
        client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception:
        return False


def check_celery_workers() -> list[str]:
    """Returns the names of Celery workers that responded to a ping --
    an empty list means no workers are currently up (or reachable)."""
    try:
        from config.celery import app as celery_app
        replies = celery_app.control.inspect(timeout=1).ping() or {}
        return list(replies.keys())
    except Exception:
        return []


def get_system_status() -> dict:
    """The full health snapshot -- same shape adminpanel's system_status
    view has always returned, now with a single source of truth."""
    from django.utils import timezone

    worker_names = check_celery_workers()

    return {
        "api": {"ok": True, "server_time": timezone.now()},
        "database": {"ok": check_database()},
        "redis": {"ok": check_redis()},
        "celery": {"ok": len(worker_names) > 0, "workers": worker_names},
    }
