"""Matches a spoken category name ("gym", "Gym", "GYM") against the
CURRENT USER's own categories -- never any other user's. Case-insensitive
exact match first, then a light fuzzy match for typos/near-misses; genuine
synonyms ("workout" for an existing "Gym" category) are left to the LLM,
which sees the user's real category list in the chat context and is
instructed to prefer an existing one when it plausibly matches -- this
function is the deterministic safety net underneath that judgment call,
not a synonym dictionary itself.
"""

from __future__ import annotations

import difflib

from categories.models import Category

_FUZZY_CUTOFF = 0.75


def resolve_category(user, name: str) -> Category | None:
    """Returns the matching Category for this user, or None if nothing
    close enough was found. Never creates anything."""
    if not name:
        return None
    name = name.strip()
    if not name:
        return None

    exact = Category.objects.filter(user=user, name__iexact=name).first()
    if exact:
        return exact

    existing = list(Category.objects.filter(user=user))
    if not existing:
        return None
    lowered = {c.name.lower(): c for c in existing}
    close = difflib.get_close_matches(name.lower(), lowered.keys(), n=1, cutoff=_FUZZY_CUTOFF)
    return lowered[close[0]] if close else None


def create_category(user, name: str) -> Category:
    return Category.objects.create(user=user, name=name.strip())


def list_category_names(user) -> list[str]:
    return list(Category.objects.filter(user=user).order_by("name").values_list("name", flat=True))
