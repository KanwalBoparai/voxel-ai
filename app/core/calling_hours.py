"""Calling-hours guard — keeps the system from dialing outside allowed times."""
from datetime import datetime
from app.core.config import settings
from app.core.business_config import business_config

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def is_within_calling_hours(now: datetime | None = None) -> bool:
    """
    True if it's currently OK to place a call.
    Rules: within CALL_START_HOUR/CALL_END_HOUR, and not a day the business is closed.
    """
    now = now or datetime.now()
    day_hours = business_config.hours.get(_WEEKDAYS[now.weekday()])
    if day_hours is not None and day_hours.closed:
        return False
    return settings.CALL_START_HOUR <= now.hour < settings.CALL_END_HOUR


def next_calling_window(now: datetime | None = None) -> datetime:
    """Return the next datetime at which calling becomes allowed."""
    from datetime import timedelta
    now = now or datetime.now()
    candidate = now
    for _ in range(8):  # at most a week out
        day_hours = business_config.hours.get(_WEEKDAYS[candidate.weekday()])
        closed = day_hours is not None and day_hours.closed
        if not closed and candidate.hour < settings.CALL_START_HOUR:
            return candidate.replace(hour=settings.CALL_START_HOUR, minute=0, second=0, microsecond=0)
        if not closed and settings.CALL_START_HOUR <= candidate.hour < settings.CALL_END_HOUR:
            return candidate
        # roll to next day's opening
        candidate = (candidate + timedelta(days=1)).replace(
            hour=settings.CALL_START_HOUR, minute=0, second=0, microsecond=0
        )
    return candidate
