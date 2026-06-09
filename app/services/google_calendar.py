"""
Google Calendar: check available slots and book free in-home measure appointments.

Setup required (see .env.example):
  GOOGLE_SERVICE_ACCOUNT_FILE  — path to a service-account JSON key file, OR
  GOOGLE_SERVICE_ACCOUNT_JSON  — the JSON content as a single env-var string
  GOOGLE_CALENDAR_ID           — the calendar ID to read/write
  APPOINTMENT_TIMEZONE         — e.g. America/Toronto

The service account must have "Make changes to events" permission on the calendar.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, date
from typing import Optional
from zoneinfo import ZoneInfo

from app.core.config import settings

SLOT_HOURS = list(range(9, 17))   # 9 AM – 4 PM start (last slot ends at 5 PM)
SLOT_DURATION = timedelta(hours=1)

_TIME_RANGES = {
    "morning":   list(range(9, 12)),
    "afternoon": list(range(12, 17)),
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _weekend_dates() -> tuple[date, date]:
    """Return (Saturday, Sunday) for the current or upcoming weekend."""
    today = datetime.now().date()
    wd = today.weekday()          # 0=Mon … 5=Sat, 6=Sun
    if wd <= 4:                   # Mon–Fri: next Saturday
        sat = today + timedelta(days=5 - wd)
    elif wd == 5:                 # Saturday: today
        sat = today
    else:                         # Sunday: yesterday
        sat = today - timedelta(days=1)
    return sat, sat + timedelta(days=1)


def _day_to_date(day_str: str) -> Optional[date]:
    sat, sun = _weekend_dates()
    d = day_str.lower()
    if "sat" in d:
        return sat
    if "sun" in d:
        return sun
    return None


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
            "note": "Calendar not configured — note the customer's preference so the store can confirm.",
        }

    target = _day_to_date(preferred_day)
    if target is None:
        return {"available_slots": [], "error": f"Unrecognised day: {preferred_day!r}"}

    tz = ZoneInfo(settings.APPOINTMENT_TIMEZONE)
    day_start = datetime(target.year, target.month, target.day, 0, 0, tzinfo=tz)
    day_end   = day_start + timedelta(days=1)

    events = svc.events().list(
        calendarId=settings.GOOGLE_CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])

    booked_hours: set[int] = set()
    for ev in events:
        raw = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
        try:
            booked_hours.add(datetime.fromisoformat(raw).astimezone(tz).hour)
        except ValueError:
            pass

    allowed = SLOT_HOURS
    trange = (preferred_time_range or "").lower()
    for key, hrs in _TIME_RANGES.items():
        if key in trange or trange in key:
            allowed = hrs
            break

    day_label = target.strftime("%A")
    slots = []
    for h in allowed:
        if h not in booked_hours:
            slots.append(f"{day_label} {datetime(2000, 1, 1, h).strftime('%-I:%M %p')}")
        if len(slots) == 3:
            break

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
            "note": "Calendar not configured — the store will confirm the appointment directly.",
        }

    target = _day_to_date(appointment_date)
    if target is None:
        return {"booked": False, "error": f"Unrecognised date: {appointment_date!r}"}

    parsed = _parse_time(appointment_time)
    if parsed is None:
        return {"booked": False, "error": f"Unrecognised time: {appointment_time!r}"}
    hour, minute = parsed

    tz = ZoneInfo(settings.APPOINTMENT_TIMEZONE)
    start_dt = datetime(target.year, target.month, target.day, hour, minute, tzinfo=tz)
    end_dt   = start_dt + SLOT_DURATION

    conflicts = svc.events().list(
        calendarId=settings.GOOGLE_CALENDAR_ID,
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
    ).execute().get("items", [])

    if conflicts:
        return {"booked": False, "error": "That slot was just taken — please offer another time."}

    event = {
        "summary": f"Free Measure Appointment - {customer_name}",
        "description": (
            f"Customer interested in Maple Carpet & Flooring's 40% off weekend sale.\n"
            f"Phone: {customer_phone}\n"
            f"Address: {customer_address}\n"
            f"Notes: {notes or 'None'}\n"
            f"Outcome: Booked"
        ),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": settings.APPOINTMENT_TIMEZONE},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": settings.APPOINTMENT_TIMEZONE},
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


async def book_measure_appointment(
    customer_name: str,
    customer_phone: str,
    appointment_date: str,
    appointment_time: str,
    customer_address: str,
    notes: str = "",
) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _book_sync,
        customer_name, customer_phone,
        appointment_date, appointment_time,
        customer_address, notes,
    )
