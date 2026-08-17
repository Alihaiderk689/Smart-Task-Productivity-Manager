from rest_framework.throttling import AnonRateThrottle


class InternalTaskRateThrottle(AnonRateThrottle):
    """Rate-limits the internal scheduled-tasks endpoint (see core/views.py)
    independent of other API traffic -- defense in depth in case
    INTERNAL_TASK_KEY ever leaks, since GitHub's cron only needs to call it
    a handful of times per hour.
    """

    scope = "internal_tasks"


class HealthRateThrottle(AnonRateThrottle):
    """Rate-limits the public health endpoint (see core/views.py::health) --
    it's unauthenticated by design, so this is the only thing standing
    between it and casual abuse. The scheduled-tasks workflow's own
    wake-up/readiness polling (a handful of requests, a few times an hour)
    stays comfortably under this."""

    scope = "health"
