from django.urls import path            #path creates a url path.
from .views import (
    confirm_password_reset,
    hello,
    login,
    logout,
    profile,
    request_password_reset,
    signup,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("hello/", hello, name="hello"),
    path("signup/", signup, name="signup"),
    path("login/", login, name="login"),
    path("profile/", profile, name="profile"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", logout, name="logout"),
    path("password-reset/", request_password_reset, name="password_reset"),
    path("password-reset/confirm/", confirm_password_reset, name="password_reset_confirm"),
]