import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

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
