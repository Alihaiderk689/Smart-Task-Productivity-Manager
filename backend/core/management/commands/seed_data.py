"""Seeds the local DB with fake users/categories/tasks/reminders so the
app can be exercised at a realistic scale (pagination, admin dashboard,
analytics) without touching real accounts.

All seeded users live under the reserved @example.test domain (RFC 6761 --
guaranteed never a real registrable domain), so `--clear` can safely find
and cascade-delete exactly what this command created and nothing else.

Usage:
    python manage.py seed_data                # 40 users, ~300 tasks
    python manage.py seed_data --users 60 --tasks 400
    python manage.py seed_data --clear         # wipe previously seeded data
"""

from __future__ import annotations

import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from categories.models import Category
from categories.services import DEFAULT_CATEGORY_NAMES
from notifications.reminder_processor import generate_reminders_for_task
from tasks.models import Task

SEED_DOMAIN = "example.test"
SEED_PASSWORD = "SeedPass123!"

FIRST_NAMES = [
    "Ava", "Liam", "Sofia", "Noah", "Mia", "Ethan", "Zara", "Omar",
    "Lena", "Kai", "Priya", "Hassan", "Nora", "Leo", "Aisha", "Marcus",
    "Yuki", "Diego", "Chloe", "Amara", "Felix", "Ingrid", "Ravi", "Elena",
    "Tariq", "Maya", "Oscar", "Sana", "Victor", "Nadia", "Jonas", "Ines",
    "Malik", "Freya", "Adrian", "Layla", "Simon", "Rosa", "Yusuf", "Clara",
]
LAST_NAMES = [
    "Khan", "Smith", "Garcia", "Müller", "Chen", "Okafor", "Kowalski",
    "Rossi", "Andersson", "Silva", "Nakamura", "Ahmed", "Novak", "Dubois",
    "Kim", "Ferreira", "Larsen", "Haddad", "Ivanov", "Costa",
]
EXTRA_CATEGORY_NAMES = [
    "Fitness", "Finance", "Reading", "Family", "Errands", "Side Project",
    "Health", "Cooking", "Home", "Volunteering",
]
TASK_VERBS = [
    "Finish", "Review", "Prepare", "Update", "Plan", "Write", "Call",
    "Email", "Organize", "Clean up", "Design", "Test", "Deploy", "Fix",
    "Research", "Schedule", "Submit", "Draft", "Present", "Analyze",
    "Follow up on", "Refactor", "Book", "Renew", "Pack for",
]
TASK_OBJECTS = [
    "the quarterly report", "the client proposal", "team meeting notes",
    "the grocery list", "the project roadmap", "the budget spreadsheet",
    "presentation slides", "the bug backlog", "onboarding docs",
    "the marketing campaign", "the database migration", "unit tests",
    "the workout plan", "the travel itinerary", "a book chapter",
    "the invoice", "my resume", "the portfolio site", "server config",
    "user feedback", "the dentist appointment", "the flight tickets",
    "the birthday gift", "the tax filing", "the code review",
]
DESC_SENTENCES = [
    "Make sure to double check everything before submitting.",
    "Need to coordinate with the team on this one.",
    "Keep it short and focused.",
    "Waiting on feedback from a couple of people first.",
    "Low effort but easy to forget.",
    "Blocks a couple of other things, so worth prioritizing.",
    "Can probably be batched with similar tasks.",
    "",
    "",
]

STATUS_WEIGHTS = [
    ("Pending", 30),
    ("In Progress", 10),
    ("Paused", 5),
    ("Completed", 40),
    ("Stopped", 5),
    ("Missed", 10),
]
PRIORITY_CHOICES = ["Low", "Medium", "High"]
DURATION_CHOICES_MIN = [30, 45, 60, 90, 120, 180, 240]


class Command(BaseCommand):
    help = "Seed the local DB with fake users, categories, tasks, and reminders for scale testing."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=40, help="Number of fake users to create.")
        parser.add_argument("--tasks", type=int, default=300, help="Number of fake tasks to create.")
        parser.add_argument("--clear", action="store_true", help="Delete previously seeded data (matched by @example.test emails) and exit.")

    def handle(self, *args, **options):
        if options["clear"]:
            self._clear()
            return

        n_users = options["users"]
        n_tasks = options["tasks"]
        now = timezone.now()

        with transaction.atomic():
            users = self._create_users(n_users)
            categories_by_user = self._create_categories(users)
            tasks = self._create_tasks(users, categories_by_user, n_tasks, now)

        reminders_created = self._create_reminders(tasks)

        n_categories = sum(len(v) for v in categories_by_user.values())
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(users)} users, {n_categories} categories, "
            f"{len(tasks)} tasks, {reminders_created} reminders."
        ))

    def _clear(self):
        qs = User.objects.filter(email__iendswith=f"@{SEED_DOMAIN}")
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Cleared {count} seeded users (cascaded categories/tasks/reminders)."))

    def _create_users(self, n):
        existing = set(
            User.objects.filter(email__iendswith=f"@{SEED_DOMAIN}").values_list("email", flat=True)
        )
        users = []
        i = 1
        while len(users) < n:
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            email = f"seed.{first.lower()}.{last.lower()}{i}@{SEED_DOMAIN}"
            i += 1
            if email in existing:
                continue
            existing.add(email)
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=first,
                last_name=last,
                password=SEED_PASSWORD,
                is_active=True,
            )
            users.append(user)
        return users

    def _create_categories(self, users):
        categories = []
        by_user = {}
        for user in users:
            names = list(DEFAULT_CATEGORY_NAMES)
            names.extend(random.sample(EXTRA_CATEGORY_NAMES, k=random.randint(0, 3)))
            user_cats = [Category(user=user, name=name, created_at=timezone.now()) for name in names]
            categories.extend(user_cats)
            by_user[user.id] = user_cats
        Category.objects.bulk_create(categories)
        return by_user

    def _create_tasks(self, users, categories_by_user, n_tasks, now):
        statuses = [s for s, _ in STATUS_WEIGHTS]
        weights = [w for _, w in STATUS_WEIGHTS]

        tasks = []
        for _ in range(n_tasks):
            user = random.choice(users)
            category = random.choice(categories_by_user[user.id])
            status = random.choices(statuses, weights=weights, k=1)[0]
            duration = timedelta(minutes=random.choice(DURATION_CHOICES_MIN))

            start_time, started_at, completed_at = self._schedule_for_status(status, duration, now)
            end_time = start_time + duration

            title = f"{random.choice(TASK_VERBS)} {random.choice(TASK_OBJECTS)}"
            description = random.choice(DESC_SENTENCES)
            created_at = now - timedelta(days=random.uniform(0, 60))

            tasks.append(Task(
                title=title[:200],
                description=description,
                user=user,
                category=category,
                priority=random.choice(PRIORITY_CHOICES),
                status=status,
                start_time=start_time,
                end_time=end_time,
                started_at=started_at,
                completed_at=completed_at,
                rescheduled_count=random.choices([0, 1, 2, 3], weights=[70, 20, 7, 3])[0],
                reminder_overdue_sent=(status == "Missed"),
                created_at=created_at,
                updated_at=created_at,
            ))
        Task.objects.bulk_create(tasks)
        return tasks

    def _schedule_for_status(self, status, duration, now):
        """Returns (start_time, started_at, completed_at) that are internally
        consistent with the given status, matching what the real lifecycle
        endpoints would have produced (see tasks.md's lifecycle rules)."""
        if status == "Pending":
            start_time = now + timedelta(days=random.uniform(-3, 15))
            return start_time, None, None

        if status in ("In Progress", "Paused"):
            start_time = now - timedelta(days=random.uniform(0.01, 10))
            started_at = start_time + timedelta(minutes=random.uniform(0, 20))
            return start_time, started_at, None

        if status in ("Completed", "Stopped"):
            start_time = now - timedelta(days=random.uniform(1, 45))
            started_at = start_time + timedelta(minutes=random.uniform(0, 15))
            completed_at = started_at + duration * random.uniform(0.5, 1.5)
            if completed_at > now:
                completed_at = now
            return start_time, started_at, completed_at

        # Missed
        start_time = now - timedelta(days=random.uniform(1, 30))
        return start_time, None, None

    def _create_reminders(self, tasks):
        from notifications.models import Reminder
        count_before = Reminder.objects.count()
        for task in tasks:
            if task.start_time > timezone.now():
                generate_reminders_for_task(task)
        return Reminder.objects.count() - count_before
