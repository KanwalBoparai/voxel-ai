"""
Google Calendar: check available slots and book appointments.

Setup required (see .env.example):
  GOOGLE_SERVICE_ACCOUNT_FILE  — path to a service-account JSON key file, OR
  GOOGLE_SERVICE_ACCOUNT_JSON  — the JSON content as a single env-var string
  GOOGLE_CALENDAR_ID           — the calendar ID to read/write

Timezone comes from config/business.json (business_config.timezone), not an env var.

The service account must have "Make changes to events" permission on the calendar.

Available hours come from config/business.json (business_config.hours) instead
of being hardcoded, so this works for any business — weekday clinics, weekend-only
pop-ups, evening restaurants, and everything in between.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, date
from typing import Optional
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.business_config import business_config

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _slot_duration() -> timedelta:
    """Appointment length from the business config (minutes), default 60."""
    return timedelta(minutes=business_config.booking.duration_minutes or 60)

_TIME_RANGES = {
    "morning":   range(0, 12),
    "afternoon": range(12, 17),
    "evening":   range(17, 24),
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _day_to_date(day_str: str) -> Optional[date]:
    """Resolve a spoken day ('today', 'tomorrow', or a weekday name) to the next such date."""
    today = datetime.now().date()
    d = (day_str or "").strip().lower()
    if "today" in d:
        return today
    if "tomorrow" in d:
        return today + timedelta(days=1)
    for i, name in enumerate(_WEEKDAYS):
        if name in d or name[:3] in d:
            delta = (i - today.weekday()) % 7
            return today + timedelta(days=delta)
    return None


def _hours_for(target: date) -> Optional[tuple[int, int]]:
    """Return (open_hour, close_hour) for this date's weekday, or None if closed."""
    day_hours = business_config.hours.get(_WEEKDAYS[target.weekday()])
    if day_hours is None or day_hours.closed:
        return None
    try:
        open_h = int(day_hours.open.split(":")[0])
        close_h = int(day_hours.close.split(":")[0])
    except (ValueError, IndexError):
        return None
    return open_h, close_h


def _credentials():
    src = settings.GOOGLE_SERVICE_ACCOUNT_JSON or ""
    path = settings.GOOGLE_SERVICE_ACCOUNT_FILE or ""
    if not src and not path:
        return None
    try:
        from google.oauth2 import service_account
        scopes = ["https://www.googleapis.com/auth/calendar"]
        if src:
            return service_account.Credentials.from_service_account_info(
                json.loads(src), scopes=scopes
            )
        return service_account.Credentials.from_service_account_file(path, scopes=scopes)
    except Exception as exc:
        print(f"[calendar] credential error: {exc}")
        return None


def _calendar_service():
    creds = _credentials()
    if creds is None:
        return None
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ── sync workers (run in thread pool) ────────────────────────────────────────

def _check_slots_sync(preferred_day: str, preferred_time_range: str) -> dict:
    svc = _calendar_service()
    if svc is None or not settings.GOOGLE_CALENDAR_ID:
        return {
            "available_slots": [],
            "note": "Calendar not configured — note the customer's preference so the business can confirm.",
        }

    target = _day_to_date(preferred_day)
    if target is None:
        return {"available_slots": [], "error": f"Unrecognised day: {preferred_day!r}"}

    business_hours = _hours_for(target)
    if business_hours is None:
        return {"available_slots": [], "note": f"We're closed on {target.strftime('%A')} — offer a different day."}
    open_h, close_h = business_hours

    tz = ZoneInfo(business_config.timezone)
    day_start = datetime(target.year, target.month, target.day, 0, 0, tzinfo=tz)
    day_end   = day_start + timedelta(days=1)

    events = svc.events().list(
        calendarId=settings.GOOGLE_CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])

    # Collect busy intervals so we can detect real overlaps (works for any
    # appointment length — a 90-min reservation blocks more than one hour).
    busy: list[tuple[datetime, datetime]] = []
    for ev in events:
        s_raw = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
        e_raw = ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date", "")
        try:
            s = datetime.fromisoformat(s_raw).astimezone(tz)
            e = datetime.fromisoformat(e_raw).astimezone(tz) if e_raw else s + _slot_duration()
            busy.append((s, e))
        except ValueError:
            pass

    # Only suggest times within the requested part of the day, if one was given.
    trange = (preferred_time_range or "").lower()
    hour_filter = None
    for key, hrs in _TIME_RANGES.items():
        if key in trange or trange in key:
            hour_filter = hrs
            break

    # Walk candidate start times from open to close, stepping by the appointment
    # length so back-to-back slots never overlap regardless of duration.
    dur = _slot_duration()
    day_label = target.strftime("%A")
    day_open = datetime(target.year, target.month, target.day, open_h, 0, tzinfo=tz)
    day_close = datetime(target.year, target.month, target.day, close_h, 0, tzinfo=tz)

    slots, cursor = [], day_open
    while cursor + dur <= day_close and len(slots) < 3:
        if hour_filter is None or cursor.hour in hour_filter:
            overlaps = any(cursor < b_end and cursor + dur > b_start for b_start, b_end in busy)
            if not overlaps:
                slots.append(f"{day_label} {cursor.strftime('%-I:%M %p')}")
        cursor += dur

    return {"available_slots": slots, "date": str(target)}


def _parse_time(time_str: str) -> Optional[tuple[int, int]]:
    """Return (hour24, minute) or None."""
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            t = datetime.strptime(time_str.strip().upper(), fmt)
            return t.hour, t.minute
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?", time_str.upper())
    if m:
        h, mn, mer = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if mer == "PM" and h != 12:
            h += 12
        elif mer == "AM" and h == 12:
            h = 0
        return h, mn
    return None


def _book_sync(
    customer_name: str, customer_phone: str,
    appointment_date: str, appointment_time: str,
    customer_address: str, notes: str,
) -> dict:
    svc = _calendar_service()
    if svc is None or not settings.GOOGLE_CALENDAR_ID:
        return {
            "booked": False,
            "note": "Calendar not configured — the business will confirm the appointment directly.",
        }

    target = _day_to_date(appointment_date)
    if target is None:
        return {"booked": False, "error": f"Unrecognised date: {appointment_date!r}"}

    parsed = _parse_time(appointment_time)
    if parsed is None:
        return {"booked": False, "error": f"Unrecognised time: {appointment_time!r}"}
    hour, minute = parsed

    tz = ZoneInfo(business_config.timezone)
    start_dt = datetime(target.year, target.month, target.day, hour, minute, tzinfo=tz)
    end_dt   = start_dt + _slot_duration()

    conflicts = svc.events().list(
        calendarId=settings.GOOGLE_CALENDAR_ID,
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
    ).execute().get("items", [])

    if conflicts:
        return {"booked": False, "error": "That slot was just taken — please offer another time."}

    label = business_config.booking.appointment_label.title()
    event = {
        "summary": f"{label} - {customer_name}",
        "description": (
            f"Booked via {business_config.business_name}'s AI voice agent.\n"
            f"Phone: {customer_phone}\n"
            f"Address: {customer_address or 'N/A'}\n"
            f"Notes: {notes or 'None'}\n"
            f"Outcome: Booked"
        ),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": business_config.timezone},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": business_config.timezone},
    }
    created = svc.events().insert(calendarId=settings.GOOGLE_CALENDAR_ID, body=event).execute()
    return {
        "booked": True,
        "event_id":   created.get("id"),
        "event_link": created.get("htmlLink"),
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "customer_address": customer_address,
    }


# ── public async API ──────────────────────────────────────────────────────────

async def check_available_slots(
    preferred_day: str,
    preferred_time_range: str = "",
    customer_phone: str = "",
) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _check_slots_sync, preferred_day, preferred_time_range
    )


async def book_appointment(
    customer_name: str,
    customer_phone: str,
    appointment_date: str,
    appointment_time: str,
    customer_address: str = "",
    notes: str = "",
) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _book_sync,
        customer_name, customer_phone,
        appointment_date, appointment_time,
        customer_address, notes,
    )
