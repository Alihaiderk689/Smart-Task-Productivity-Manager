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
    verify_email_otp,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("hello/", hello, name="hello"),
    path("signup/", signup, name="signup"),
    path("login/", login, name="login"),
    path("google-login/", google_login, name="google_login"),
    path("profile/", profile, name="profile"),
    path("profile/change-password/", change_password, name="change_password"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", logout, name="logout"),
    path("password-reset/", request_password_reset, name="password_reset"),
    path("password-reset/confirm/", confirm_password_reset, name="password_reset_confirm"),
    path("verify-email/", verify_email_otp, name="verify_email"),
    path("verify-email/resend/", resend_email_verification, name="resend_email_verification"),
]