"""Timezone-aware time helpers. Nothing in AlgoViz uses naive datetimes."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(UTC)


def from_ms(ms: int | float) -> datetime:
    """Exchange millisecond epoch → aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def to_ms(dt: datetime) -> int:
    """Aware datetime → millisecond epoch."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
