from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime, timezone
import pandas as pd
import io
import phonenumbers

from app.db.database import get_db
from app.db.models import Customer, Campaign, Call, CallStatus
from app.services.caller import make_call

router = APIRouter(prefix="/api", tags=["campaigns"])


# ---------- Schemas ----------

class CampaignCreate(BaseModel):
    name: str
    script_key: str = "default"  # keypad-flow script key (see app/scripts/templates.py)


class CampaignResponse(BaseModel):
    id: int
    name: str
    script_key: str
    active: bool
    total_calls: int = 0


class CallStats(BaseModel):
    total: int
    completed: int
    no_answer: int
    voicemail: int
    interested: int
    not_interested: int
    callbacks: int
    transferred: int


# ---------- Customers ----------

@router.post("/customers/upload")
async def upload_customers(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """
    Upload a CSV of customers. Required columns: name, phone
    Optional columns: email
    """
    contents = await file.read()
    df = pd.read_csv(io.BytesIO(contents))

    required = {"name", "phone"}
    if not required.issubset(set(df.columns.str.lower())):
        raise HTTPException(400, "CSV must have 'name' and 'phone' columns")

    df.columns = df.columns.str.lower()

    added, skipped, invalid = 0, 0, 0
    for _, row in df.iterrows():
        raw_phone = str(row["phone"]).strip()
        try:
            parsed = phonenumbers.parse(raw_phone, "US")
            if not phonenumbers.is_valid_number(parsed):
                invalid += 1
                continue
            e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            invalid += 1
            continue

        existing = await db.execute(select(Customer).where(Customer.phone == e164))
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        customer = Customer(
            name=str(row["name"]).strip(),
            phone=e164,
            email=str(row.get("email", "")).strip() or None,
        )
        db.add(customer)
        added += 1

    await db.commit()
    return {"added": added, "skipped_duplicates": skipped, "invalid_phones": invalid}


@router.get("/customers")
async def list_customers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).order_by(Customer.created_at.desc()).limit(200))
    customers = result.scalars().all()
    return [
        {"id": c.id, "name": c.name, "phone": c.phone, "do_not_call": c.do_not_call}
        for c in customers
    ]


# ---------- Campaigns ----------

@router.post("/campaigns")
async def create_campaign(data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    from app.scripts.templates import SCRIPTS
    if data.script_key not in SCRIPTS:
        raise HTTPException(400, f"script_key must be one of: {list(SCRIPTS)}")

    campaign = Campaign(name=data.name, script_key=data.script_key)
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {"id": campaign.id, "name": campaign.name, "script_key": campaign.script_key}


@router.get("/campaigns")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    return [{"id": c.id, "name": c.name, "script_key": c.script_key, "active": c.active} for c in result.scalars()]


# ---------- Launch Calls ----------

async def _launch_calls_bg(campaign_id: int, customer_ids: list[int]):
    """Background task: create call records and dial each customer."""
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        for cid in customer_ids:
            result = await db.execute(select(Customer).where(Customer.id == cid))
            customer = result.scalar_one_or_none()
            if not customer or customer.do_not_call:
                continue

            call = Call(
                customer_id=cid,
                campaign_id=campaign_id,
                status=CallStatus.pending,
                scheduled_at=datetime.now(timezone.utc),
            )
            db.add(call)
            await db.flush()  # get call.id before committing

            try:
                sid = make_call(customer.phone, call.id)
                call.twilio_call_sid = sid
                call.status = CallStatus.in_progress
            except Exception as e:
                call.status = CallStatus.failed
                call.notes = str(e)

            await db.commit()


@router.post("/campaigns/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    customer_ids: list[int] | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Launch outbound calls for a campaign.
    If customer_ids is omitted, calls ALL customers not on DNC list.
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    if customer_ids is None:
        result = await db.execute(
            select(Customer.id).where(Customer.do_not_call == False)
        )
        customer_ids = [row[0] for row in result.fetchall()]

    if not customer_ids:
        raise HTTPException(400, "No eligible customers to call")

    background_tasks.add_task(_launch_calls_bg, campaign_id, customer_ids)
    return {"message": f"Launching calls to {len(customer_ids)} customers", "campaign_id": campaign_id}


# ---------- Stats ----------

@router.get("/campaigns/{campaign_id}/stats")
async def campaign_stats(campaign_id: int, db: AsyncSession = Depends(get_db)) -> CallStats:
    result = await db.execute(select(Call).where(Call.campaign_id == campaign_id))
    calls = result.scalars().all()

    from app.db.models import CallOutcome
    return CallStats(
        total=len(calls),
        completed=sum(1 for c in calls if c.status == CallStatus.completed),
        no_answer=sum(1 for c in calls if c.status == CallStatus.no_answer),
        voicemail=sum(1 for c in calls if c.status == CallStatus.voicemail),
        interested=sum(1 for c in calls if c.outcome == CallOutcome.interested),
        not_interested=sum(1 for c in calls if c.outcome == CallOutcome.not_interested),
        callbacks=sum(1 for c in calls if c.outcome == CallOutcome.callback_requested),
        transferred=sum(1 for c in calls if c.outcome == CallOutcome.transferred),
    )
