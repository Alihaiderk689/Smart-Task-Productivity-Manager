from django.urls import path

from . import views

urlpatterns = [
    path("overview/", views.admin_overview, name="admin-overview"),
    path("system-status/", views.system_status, name="admin-system-status"),

    path("users/", views.AdminUserListView.as_view(), name="admin-user-list"),
    path("users/<int:pk>/", views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("users/<int:user_id>/tasks/", views.AdminUserTasksListView.as_view(), name="admin-user-tasks"),
    path("users/<int:user_id>/deactivate/", views.deactivate_user, name="admin-deactivate-user"),
    path("users/<int:user_id>/activate/", views.activate_user, name="admin-activate-user"),
    path("users/<int:user_id>/delete/", views.delete_user, name="admin-delete-user"),

    path("categories/names/", views.distinct_category_names, name="admin-category-names"),

    path("tasks/", views.AdminTaskListView.as_view(), name="admin-task-list"),
    path("tasks/<int:pk>/", views.AdminTaskDetailView.as_view(), name="admin-task-detail"),
    path("tasks/<int:task_id>/trigger-reminder/", views.trigger_reminder, name="admin-trigger-reminder"),

    path("reports/users.csv", views.export_users_csv, name="admin-export-users-csv"),
    path("reports/tasks.csv", views.export_tasks_csv, name="admin-export-tasks-csv"),
]
