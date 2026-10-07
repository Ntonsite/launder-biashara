from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ..core.config import settings

LOCAL_TZ = ZoneInfo(settings.timezone)


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def as_utc(value: datetime) -> datetime:
    """Normalise to UTC; naive values (e.g. from client input) are taken as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
