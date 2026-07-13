from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from categories.models import Category
from .models import Task


class TaskModelTest(TestCase):
    def test_task_query_works_with_current_schema(self):
        self.assertEqual(Task.objects.count(), 0)


class TaskCreationTest(TestCase):
    def test_task_can_be_created_without_due_date(self):
        user = User.objects.create_user(username="taskuser", email="taskuser@example.com", password="testpass123")
        category = Category.objects.create(user=user, name="General")

        task = Task.objects.create(
            user=user,
            category=category,
            title="Regression test task",
            description="This should be created successfully",
            priority="Medium",
            status="Pending",
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
        )

        self.assertEqual(task.title, "Regression test task")
        self.assertEqual(task.status, "Pending")
