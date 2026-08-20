from rest_framework.throttling import UserRateThrottle


class EvaluationRunRateThrottle(UserRateThrottle):
    """Rate-limits triggering the evaluation suite (see
    views.py::trigger_evaluation) per admin user. Each run executes ~22
    scenarios of real, billed LLM calls and takes tens of seconds -- by far
    the most expensive single endpoint in the app -- so this is deliberately
    much tighter than copilot chat's throttle.
    """

    scope = "evaluation_run"
