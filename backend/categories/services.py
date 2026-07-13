from .models import Category

DEFAULT_CATEGORY_NAMES = [
    "Study",
    "Work",
    "Personal",
    "Meetings",
    "Travel",
    "Calls",
    "Events",
]


def create_default_categories(user):
    """Seed a new user's account with a standard set of categories so they
    don't have to build the common ones themselves."""
    existing_lower = set(
        Category.objects.filter(user=user).values_list("name", flat=True)
    )
    existing_lower = {name.lower() for name in existing_lower}

    for name in DEFAULT_CATEGORY_NAMES:
        if name.lower() in existing_lower:
            continue
        Category.objects.create(user=user, name=name)
