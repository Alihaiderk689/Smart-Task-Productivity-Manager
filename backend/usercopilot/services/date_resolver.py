"""Deterministic date/time handling for the User Copilot.

Design: the LLM is told the current server date/time/weekday/timezone (see
current_context_line()) and instructed to resolve relative phrases
("tomorrow", "next Friday", "this weekend", "3pm") into full ISO 8601
datetimes itself before calling a tool -- LLMs are already reliable at this
kind of natural-language date resolution when given a concrete reference
point, and hand-rolling a rule-based parser for the open-ended space of
things people actually say ("in a few days", "next next Monday", "the
15th") would be its own large, bug-prone project.

What stays deterministic and LLM-free is everything after that: parsing
the ISO string, rejecting anything malformed, and attaching the server's
timezone -- resolve_datetime() below, called from every tool that accepts
a date, never trusts the LLM's output without re-parsing and validating it
in plain Python.
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def resolve_datetime(value):
    """Parses an ISO 8601 datetime string into a timezone-aware datetime
    in the server's local timezone. Returns (parsed_datetime_or_None,
    error_message) -- never raises."""
    if not value or not isinstance(value, str):
        return None, "Missing date/time value."
    parsed = parse_datetime(value)
    if parsed is None:
        return None, f"Could not understand the date/time {value!r} -- expected something like 2026-08-15T15:00:00."
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed, ""


def format_friendly(dt) -> str:
    """Human-friendly, localized rendering for anything shown to the user in
    chat (e.g. "Aug 9, 2026, 02:00 PM") -- tool results should always use
    this instead of dt.isoformat(), which leaks a raw UTC offset the LLM
    tends to repeat verbatim back to the user."""
    return timezone.localtime(dt).strftime("%b %d, %Y, %I:%M %p")


def current_context_line() -> str:
    """One line for the chat system prompt giving the LLM "now", so it can
    resolve relative phrases into real ISO datetimes on its own."""
    now = timezone.localtime(timezone.now())
    tz_name = timezone.get_current_timezone_name()
    return (
        f"Right now it is {now.strftime('%A, %Y-%m-%d %H:%M')} ({tz_name}). "
        "Always resolve relative dates/times (\"tomorrow\", \"next Friday\", \"this weekend\", "
        "\"morning\" ~9am, \"afternoon\" ~2pm, \"evening\" ~6pm, \"night\" ~9pm) against this moment, "
        "and always pass full ISO 8601 datetimes (e.g. \"2026-08-15T15:00:00\") as tool arguments -- "
        "never pass a bare phrase like \"tomorrow\" directly to a tool."
    )
