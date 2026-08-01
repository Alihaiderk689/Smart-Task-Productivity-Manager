"""Copilot-specific permissions. Re-exports IsAdminUser for a single,
obvious import path within this app -- add finer-grained permissions here
(e.g. "can approve sensitive actions" vs. "can only view") as the approval
workflow is built out; every endpoint in this app is admin-only for now,
same as adminpanel."""

from rest_framework.permissions import IsAdminUser

__all__ = ["IsAdminUser"]
