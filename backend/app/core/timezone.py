from datetime import datetime, timezone
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def to_app_timezone(value: datetime | None) -> datetime | None:
    """Convert a datetime value to the application timezone used by API responses."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(APP_TIMEZONE)


def now_utc() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def now_app_timezone() -> datetime:
    """Return the current timezone-aware datetime in Asia/Ho_Chi_Minh."""
    return datetime.now(APP_TIMEZONE)
