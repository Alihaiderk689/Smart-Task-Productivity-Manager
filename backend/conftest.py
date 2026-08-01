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

@pytest.fixture(autouse=True)
def _use_local_file_storage(settings):
    # Avatar uploads use Cloudinary in real environments (see
    # config/settings.py), but tests must stay hermetic -- otherwise every
    # test run uploads real junk images to the live Cloudinary account over
    # the network. Force plain local storage for the duration of each test.
    settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

@pytest.fixture(autouse=True)
def _no_real_llm_key(settings):
    # backend/.env carries a real GROQ_API_KEY for the running app, but
    # tests must stay hermetic -- otherwise any copilot test that forgets
    # to mock the LLM silently makes a real network call to Groq. Force it
    # unset by default; tests that specifically exercise the "configured"
    # path set settings.GROQ_API_KEY back explicitly within the test.
    settings.GROQ_API_KEY = ""

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
def other_user(db):
    # A second, distinct account -- for proving one user's authenticated
    # session can't reach another user's data (object-level authorization,
    # not just "is someone logged in").
    return User.objects.create_user(
        username="otheruser@example.com",
        email="otheruser@example.com",
        password="OtherPass123!"
    )

@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staffuser@example.com",
        email="staffuser@example.com",
        password="StaffPass123!",
        is_staff=True,
    )

@pytest.fixture
def staff_client(api_client, staff_user):
    refresh = RefreshToken.for_user(staff_user)
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
