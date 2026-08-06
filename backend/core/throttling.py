from rest_framework.throttling import AnonRateThrottle


class InternalTaskRateThrottle(AnonRateThrottle):
    """Rate-limits the internal scheduled-tasks endpoint (see core/views.py)
    independent of other API traffic -- defense in depth in case
    INTERNAL_TASK_KEY ever leaks, since GitHub's cron only needs to call it
    a handful of times per hour.
    """

    scope = "internal_tasks"
