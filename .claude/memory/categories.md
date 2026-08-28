---
name: categories
description: Per-user task tags, unique per (user, name), auto-seeded with 7 defaults on signup.
app: categories
updated: 2026-08-28
---

## What it does

Simple per-user tagging for tasks. `Category(user, name)` with
`unique_together = ("user", "name")` — the same name can exist for
different users, never twice for one user.

## Key files

- `backend/categories/models.py` — the `Category` model.
- `backend/categories/services.py` — `create_default_categories(user)`:
  seeds `Study, Work, Personal, Meetings, Travel, Calls, Events`
  case-insensitively (skips any name the user already has, so it's safe
  to call more than once). Check the signup flow in `users/views.py` if
  you need to find where this is actually invoked.
- `backend/categories/views.py`, `urls.py`, `serializers.py`.

## Invariants / gotchas

- Name matching for the default-seed skip is **case-insensitive**
  (`existing_lower`), but the DB `unique_together` constraint itself is
  case-sensitive — a user could still end up with both "Work" and "work"
  if created through two different paths that don't both go through
  `create_default_categories`'s dedup logic. Worth checking if you ever
  see duplicate-looking categories.
- `Task.category` is `on_delete=models.CASCADE` — deleting a category
  deletes every task in it. There's no "reassign tasks then delete"
  UX/endpoint currently; confirm this is intended behavior before adding
  a category-delete surface anywhere new.

## Touches / related

[tasks.md](tasks.md) (FK from `Task`), [adminpanel.md](adminpanel.md)
(`distinct_category_names` endpoint reads across all users, staff-only).
