"""Application timezone helpers."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import TARGET_TIMEZONE


TARGET_TZ = ZoneInfo(TARGET_TIMEZONE)
UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime, treating legacy naive values as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_utc_naive(value: datetime) -> datetime:
    """Normalize a timestamp for legacy TIMESTAMP WITHOUT TIME ZONE columns."""
    return ensure_utc(value).replace(tzinfo=None)
