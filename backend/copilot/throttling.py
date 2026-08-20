from rest_framework.throttling import UserRateThrottle


class ChatRateThrottle(UserRateThrottle):
    """Rate-limits the admin copilot chat endpoint (see views.py::chat_send)
    per admin user, independent of other API traffic -- each message
    triggers a real, billed LLM call (Groq/Gemini/OpenRouter), so with no
    limit here a compromised staff account, a runaway frontend retry loop,
    or just an over-eager admin could run up real API cost with nothing in
    the way. UserRateThrottle (not AnonRateThrottle) since this endpoint is
    always authenticated -- it keys per user id, not per IP.
    """

    scope = "copilot_chat"
