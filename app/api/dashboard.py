"""
Dashboard API — read-only aggregates for the business-owner dashboard.

Returns live data from the database when it exists (real calls, appointments,
outcomes) plus integration connection status derived from configured secrets.
The frontend falls back to illustrative sample data when the DB is empty, so a
fresh clone still shows a populated, realistic dashboard.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Call, Customer, Appointment, CallOutcome, CallStatus
from app.core.config import settings

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _integration_status() -> dict:
    google = bool(settings.GOOGLE_SERVICE_ACCOUNT_FILE or settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    return {
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "twilio": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN),
        "vapi": bool(settings.VAPI_API_KEY),
        "elevenlabs": bool(settings.ELEVENLABS_API_KEY),
        "google_calendar": bool(google and settings.GOOGLE_CALENDAR_ID),
        "google_sheets": bool(google and settings.GOOGLE_SHEET_ID),
    }


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    total_calls = (await db.execute(select(func.count(Call.id)))).scalar() or 0
    total_customers = (await db.execute(select(func.count(Customer.id)))).scalar() or 0
    total_appts = (await db.execute(select(func.count(Appointment.id)))).scalar() or 0

    outcome_rows = (await db.execute(
        select(Call.outcome, func.count(Call.id)).group_by(Call.outcome)
    )).all()
    outcomes = {(o.value if o else "unknown"): c for o, c in outcome_rows}

    avg_duration = (await db.execute(
        select(func.avg(Call.duration_seconds)).where(Call.duration_seconds.isnot(None))
    )).scalar()

    return {
        "has_data": total_calls > 0,
        "totals": {
            "calls": total_calls,
            "customers": total_customers,
            "appointments": total_appts,
            "avg_duration_seconds": round(avg_duration) if avg_duration else 0,
        },
        "outcomes": outcomes,
        "integrations": _integration_status(),
    }


@router.get("/calls")
async def recent_calls(limit: int = 25, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Call, Customer)
        .join(Customer, Call.customer_id == Customer.id)
        .order_by(Call.created_at.desc())
        .limit(limit)
    )).all()

    calls = []
    for call, customer in rows:
        turns = []
        for t in (call.transcript or []):
            content = t.get("content", "")
            if isinstance(content, str) and content.startswith("<call_connected>"):
                continue
            if isinstance(content, str) and content:
                turns.append({"role": t.get("role"), "text": content})
        calls.append({
            "id": call.id,
            "customer": customer.name,
            "phone": customer.phone,
            "status": call.status.value if call.status else None,
            "outcome": call.outcome.value if call.outcome else None,
            "duration_seconds": call.duration_seconds,
            "lead_score": customer.lead_score,
            "created_at": (call.created_at or datetime.now(timezone.utc)).isoformat(),
            "turns": turns,
        })
    return {"calls": calls}
