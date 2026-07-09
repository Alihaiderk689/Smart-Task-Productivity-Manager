from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/tasks/", include("tasks.urls")),
    # Authentication APIs
    path("api/", include("users.urls")),

    # Category APIs
    path("api/categories/", include("categories.urls")),
]