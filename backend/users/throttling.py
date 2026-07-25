from rest_framework.throttling import AnonRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    """Rate-limits sensitive anonymous auth endpoints (signup, login,
    password reset) per client IP, independent of any other API traffic.

    Note: AnonRateThrottle (not ScopedRateThrottle) on purpose -- Scoped's
    scope comes from the *view class's* `throttle_scope` attribute, which
    plain @api_view function views don't have, so it silently never throttles
    them. AnonRateThrottle reads `scope` directly off this class instead.
    """

    scope = "auth"
