"""Timestamp helpers.

All timestamps are timezone-aware UTC ``datetime`` objects, serialized in ISO
8601 form. Using one canonical representation avoids ambiguity in the
domain model and in serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(UTC)
