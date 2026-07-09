from django.urls import path
from .views import signup, hello, login, profile, logout
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("hello/", hello, name="hello"),
    path("signup/", signup, name="signup"),
    path("login/", login, name="login"),
    path("profile/", profile, name="profile"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", logout, name="logout"),
]