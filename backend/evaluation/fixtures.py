"""Ephemeral data the evaluation suite needs to exercise real workflows
(a dormant user to propose deactivating, an overdue task to propose a
reminder for, an old completed task to propose deleting). Everything this
factory creates is tracked and torn down at the end of the run -- the
suite runs against the real database (same as any agent triggered from the
UI), so it must not leave synthetic users/tasks/recommendations behind.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.utils import timezone

from categories.models import Category
from copilot.models import Recommendation
from tasks.models import Task


class EvalFixtures:
    def __init__(self):
        self._users: list[int] = []
        self._tasks: list[int] = []
        self._categories: list[int] = []
        self._recommendations: list[int] = []

    def regular_user(self) -> User:
        email = f"eval-fixture-{uuid.uuid4().hex[:10]}@example.com"
        user = User.objects.create_user(username=email, email=email, password="EvalFixture123!")
        self._users.append(user.id)
        return user

    def dormant_user(self, *, days_inactive: int = 100) -> User:
        user = self.regular_user()
        user.last_login = timezone.now() - timezone.timedelta(days=days_inactive)
        user.save(update_fields=["last_login"])
        return user

    def category(self, *, user: User, name: str = "Eval") -> Category:
        cat = Category.objects.create(user=user, name=f"{name} {uuid.uuid4().hex[:6]}")
        self._categories.append(cat.id)
        return cat

    def overdue_task(self, *, user: User, minutes_overdue: int = 10, reminder_sent: bool = False) -> Task:
        cat = self.category(user=user)
        now = timezone.now()
        task = Task.objects.create(
            title=f"[EVAL] Overdue task {uuid.uuid4().hex[:6]}",
            user=user,
            category=cat,
            status="Pending",
            start_time=now - timezone.timedelta(hours=2),
            end_time=now - timezone.timedelta(minutes=minutes_overdue),
            reminder_overdue_sent=reminder_sent,
        )
        self._tasks.append(task.id)
        return task

    def old_completed_task(self, *, user: User, days_ago: int = 40) -> Task:
        cat = self.category(user=user)
        now = timezone.now()
        task = Task.objects.create(
            title=f"[EVAL] Old completed task {uuid.uuid4().hex[:6]}",
            user=user,
            category=cat,
            status="Completed",
            start_time=now - timezone.timedelta(days=days_ago, hours=2),
            end_time=now - timezone.timedelta(days=days_ago, hours=1),
            completed_at=now - timezone.timedelta(days=days_ago),
        )
        self._tasks.append(task.id)
        return task

    def track_recommendation(self, rec_id: int):
        self._recommendations.append(rec_id)

    def cleanup(self):
        # Deliberately does NOT touch AgentRun rows -- those are genuine
        # history of real agent executions against real data (the same
        # kind of row a real admin's "Run Now" click produces) and are
        # worth keeping. Only synthetic fixture data and the recommendations
        # scoped to it get removed.
        #
        # Fixture data is live in the same database every other scenario in
        # the run reads from -- a *different*, untracked agent invocation
        # (e.g. the deterministic "user_monitoring_agent_run" scenario) can
        # legitimately observe a fixture user/task another scenario created
        # earlier in the same run and raise its own recommendation about it.
        # That recommendation was never passed to track_recommendation(), so
        # catch it here by reference before the object it points at (which
        # has no FK/cascade -- action_payload is a plain JSON blob) disappears
        # and leaves an orphaned row behind.
        if self._users:
            Recommendation.objects.filter(action_payload__input__user_id__in=self._users).delete()
        if self._tasks:
            Recommendation.objects.filter(action_payload__input__task_id__in=self._tasks).delete()

        Recommendation.objects.filter(id__in=self._recommendations).delete()
        Task.objects.filter(id__in=self._tasks).delete()
        Category.objects.filter(id__in=self._categories).delete()
        User.objects.filter(id__in=self._users).delete()
