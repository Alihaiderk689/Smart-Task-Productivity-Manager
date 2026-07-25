import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework_simplejwt.tokens import RefreshToken

@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    # DRF throttling (see users/throttling.py) counts requests via Django's
    # cache, which persists across tests in the same run. Without this,
    # enough login/signup/password-reset calls across the suite trip the
    # real rate limit and unrelated tests start failing with 429s.
    cache.clear()
    yield

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def test_user(db):
    user = User.objects.create_user(
        username="testuser@example.com",
        email="testuser@example.com",
        password="TestPass123!"
    )
    user.first_name = "Test"
    user.save()
    return user

@pytest.fixture
def auth_client(api_client, test_user):
    refresh = RefreshToken.for_user(test_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client

@pytest.fixture
def category_factory(db, test_user):
    from categories.models import Category
    def _create_category(name="General", user=test_user):
        return Category.objects.create(name=name, user=user)
    return _create_category

@pytest.fixture
def task_factory(db, test_user):
    from tasks.models import Task
    from django.utils import timezone
    def _create_task(title="Test Task", user=test_user, category=None, **kwargs):
        if not category:
            from categories.models import Category
            category, _ = Category.objects.get_or_create(name="General", user=user)
        
        start_time = kwargs.pop("start_time", timezone.now())
        end_time = kwargs.pop("end_time", timezone.now() + timezone.timedelta(hours=1))
        
        return Task.objects.create(
            title=title,
            user=user,
            category=category,
            start_time=start_time,
            end_time=end_time,
            **kwargs
        )
    return _create_task
