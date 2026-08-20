from django.urls import path            #path creates a url path.
from .views import (
    change_password,
    confirm_password_reset,
    google_login,
    hello,
    login,
    logout,
    profile,
    request_password_reset,
    resend_email_verification,
    signup,
    token_refresh,
    verify_email_otp,
)

urlpatterns = [
    path("hello/", hello, name="hello"),
    path("signup/", signup, name="signup"),
    path("login/", login, name="login"),
    path("google-login/", google_login, name="google_login"),
    path("profile/", profile, name="profile"),
    path("profile/change-password/", change_password, name="change_password"),
    # Custom view (not rest_framework_simplejwt's stock TokenRefreshView) --
    # reads the refresh token from an HttpOnly cookie instead of the
    # request body. See users/views.py::token_refresh and
    # users/token_cookies.py for why.
    path("token/refresh/", token_refresh, name="token_refresh"),
    path("logout/", logout, name="logout"),
    path("password-reset/", request_password_reset, name="password_reset"),
    path("password-reset/confirm/", confirm_password_reset, name="password_reset_confirm"),
    path("verify-email/", verify_email_otp, name="verify_email"),
    path("verify-email/resend/", resend_email_verification, name="resend_email_verification"),
]