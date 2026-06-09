"""Calling-hours guard — keeps the system from dialing outside allowed times."""
from datetime import datetime
from app.core.config import settings


def is_within_calling_hours(now: datetime | None = None) -> bool:
    """
    True if it's currently OK to place a call.
    Rules: between CALL_START_HOUR and CALL_END_HOUR, and not Sunday (weekday 6).
    """
    now = now or datetime.now()
    if now.weekday() == 6:  # Sunday
        return False
    return settings.CALL_START_HOUR <= now.hour < settings.CALL_END_HOUR


def next_calling_window(now: datetime | None = None) -> datetime:
    """Return the next datetime at which calling becomes allowed."""
    from datetime import timedelta
    now = now or datetime.now()
    candidate = now
    # Advance until we land inside a valid window
    while True:
        if candidate.weekday() != 6 and candidate.hour < settings.CALL_START_HOUR:
            return candidate.replace(hour=settings.CALL_START_HOUR, minute=0, second=0, microsecond=0)
        if candidate.weekday() != 6 and settings.CALL_START_HOUR <= candidate.hour < settings.CALL_END_HOUR:
            return candidate
        # roll to next day's opening
        candidate = (candidate + timedelta(days=1)).replace(
            hour=settings.CALL_START_HOUR, minute=0, second=0, microsecond=0
        )
