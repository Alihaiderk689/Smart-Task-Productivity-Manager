from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin        #django built in admin panel.
from django.urls import path, include          #django built in urls module to include urls from other apps.


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/tasks/", include("tasks.urls")),
    path("api/", include("users.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/categories/", include("categories.urls")),
    path("api/analytics/", include("analytics.urls")),
    path("api/admin/", include("adminpanel.urls")),
    path("api/copilot/", include("copilot.urls")),
    path("api/evaluation/", include("evaluation.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)