"""
Google Sheets CRM: save call outcomes to a spreadsheet visible to the store owner.

Setup required (see .env.example):
  GOOGLE_SERVICE_ACCOUNT_FILE  — path to service-account JSON key file, OR
  GOOGLE_SERVICE_ACCOUNT_JSON  — the JSON content as an env-var string
  GOOGLE_SHEET_ID              — the spreadsheet ID (from its URL)

The service account must have "Editor" access on the spreadsheet.
The sheet "Call Outcomes" is created automatically if it does not exist.
"""

import asyncio
import json
from datetime import datetime, timezone

from app.core.config import settings

_HEADERS = [
    "Timestamp", "Customer Name", "Phone", "Outcome",
    "Appointment Date", "Appointment Time", "Address",
    "Callback Time", "Notes", "Do Not Call",
]

_ALLOWED_OUTCOMES = {
    "booked", "interested", "not_interested",
    "callback", "do_not_call", "voicemail",
    "wrong_number", "bad_timing",
}


def _credentials():
    src  = settings.GOOGLE_SERVICE_ACCOUNT_JSON or ""
    path = settings.GOOGLE_SERVICE_ACCOUNT_FILE or ""
    if not src and not path:
        return None
    try:
        from google.oauth2 import service_account
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if src:
            return service_account.Credentials.from_service_account_info(
                json.loads(src), scopes=scopes
            )
        return service_account.Credentials.from_service_account_file(path, scopes=scopes)
    except Exception as exc:
        print(f"[sheets] credential error: {exc}")
        return None


def _save_sync(
    customer_name: str,
    customer_phone: str,
    outcome: str,
    appointment_date: str,
    appointment_time: str,
    customer_address: str,
    callback_time: str,
    notes: str,
    do_not_call: bool,
) -> dict:
    if outcome not in _ALLOWED_OUTCOMES:
        outcome = "not_interested"   # safe fallback — never write arbitrary strings

    # Always log to console for local dev visibility.
    print(
        f"[crm] outcome={outcome!r} name={customer_name!r} phone={customer_phone!r}"
        + (f" appt={appointment_date} {appointment_time}" if appointment_date else "")
    )

    creds = _credentials()
    if creds is None or not settings.GOOGLE_SHEET_ID:
        return {"saved": False, "reason": "sheets_not_configured"}

    try:
        import gspread
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(settings.GOOGLE_SHEET_ID)

        try:
            ws = sh.worksheet("Call Outcomes")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet("Call Outcomes", rows=1000, cols=len(_HEADERS))
            ws.append_row(_HEADERS, value_input_option="RAW")

        ws.append_row([
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            customer_name,
            customer_phone,
            outcome,
            appointment_date,
            appointment_time,
            customer_address,
            callback_time,
            notes,
            "Yes" if do_not_call else "No",
        ], value_input_option="USER_ENTERED")

        return {"saved": True}

    except Exception as exc:
        print(f"[sheets] write error: {exc}")
        return {"saved": False, "error": str(exc)}


async def save_call_outcome(
    customer_name: str,
    customer_phone: str,
    outcome: str,
    appointment_date: str = "",
    appointment_time: str = "",
    customer_address: str = "",
    callback_time: str = "",
    notes: str = "",
    do_not_call: bool = False,
) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _save_sync,
        customer_name, customer_phone, outcome,
        appointment_date, appointment_time,
        customer_address, callback_time,
        notes, do_not_call,
    )
