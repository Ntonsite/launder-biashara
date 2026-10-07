from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ..core.config import settings

LOCAL_TZ = ZoneInfo(settings.timezone)


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC, which is how they were written."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
