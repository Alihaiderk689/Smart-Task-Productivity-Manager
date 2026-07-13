import pytest
from rest_framework import status
from categories.models import Category
from categories.services import DEFAULT_CATEGORY_NAMES, create_default_categories

@pytest.mark.django_db
def test_create_default_categories_seeds_expected_names(test_user):
    create_default_categories(test_user)
    names = set(Category.objects.filter(user=test_user).values_list("name", flat=True))
    assert names == set(DEFAULT_CATEGORY_NAMES)

@pytest.mark.django_db
def test_create_default_categories_skips_existing_case_insensitive(test_user, category_factory):
    category_factory(name="study", user=test_user)
    create_default_categories(test_user)

    names = list(Category.objects.filter(user=test_user, name__iexact="study"))
    assert len(names) == 1
    assert names[0].name == "study"

@pytest.mark.django_db
def test_list_categories(auth_client, test_user, category_factory):
    category_factory(name="Personal", user=test_user)
    category_factory(name="Work", user=test_user)
    
    # Create category for another user
    from django.contrib.auth.models import User
    other_user = User.objects.create_user(username="other@example.com", password="Password123!")
    category_factory(name="Other User Category", user=other_user)
    
    response = auth_client.get("/api/categories/")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 2
    names = [c["name"] for c in response.data]
    assert "Personal" in names
    assert "Work" in names
    assert "Other User Category" not in names

@pytest.mark.django_db
def test_create_category_success(auth_client, test_user):
    response = auth_client.post(
        "/api/categories/",
        {"name": "Exercise"},
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert Category.objects.filter(name="Exercise", user=test_user).exists()

@pytest.mark.django_db
def test_create_category_duplicate_name_for_same_user(auth_client, test_user, category_factory):
    category_factory(name="Work", user=test_user)
    response = auth_client.post(
        "/api/categories/",
        {"name": "Work"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_create_category_duplicate_name_case_insensitive(auth_client, test_user, category_factory):
    category_factory(name="Work", user=test_user)
    response = auth_client.post(
        "/api/categories/",
        {"name": "work"},
        format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_create_category_same_name_different_users(auth_client, test_user, category_factory):
    from django.contrib.auth.models import User
    other_user = User.objects.create_user(username="other@example.com", password="Password123!")
    category_factory(name="Work", user=other_user)
    
    response = auth_client.post(
        "/api/categories/",
        {"name": "Work"},
        format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert Category.objects.filter(name="Work", user=test_user).exists()
    assert Category.objects.filter(name="Work", user=other_user).exists()

@pytest.mark.django_db
def test_get_single_category_success(auth_client, test_user, category_factory):
    category = category_factory(name="Personal", user=test_user)
    response = auth_client.get(f"/api/categories/{category.id}/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Personal"

@pytest.mark.django_db
def test_get_single_category_unauthorized(auth_client, category_factory):
    from django.contrib.auth.models import User
    other_user = User.objects.create_user(username="other@example.com", password="Password123!")
    other_category = category_factory(name="Other Personal", user=other_user)
    
    response = auth_client.get(f"/api/categories/{other_category.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.django_db
def test_update_category_success(auth_client, test_user, category_factory):
    category = category_factory(name="Old Name", user=test_user)
    response = auth_client.put(
        f"/api/categories/{category.id}/",
        {"name": "New Name"},
        format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    category.refresh_from_db()
    assert category.name == "New Name"

@pytest.mark.django_db
def test_delete_category_success(auth_client, test_user, category_factory):
    category = category_factory(name="Temporary", user=test_user)
    response = auth_client.delete(f"/api/categories/{category.id}/")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Category.objects.filter(id=category.id).exists()
