from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone

from app.db.database import get_db
from app.db.models import Call, Customer, Campaign, CallStatus, CallOutcome
from app.services.voice import generate_and_cache
from app.services.caller import (
    twiml_play_gather,
    twiml_play_and_end,
    twiml_transfer,
    twiml_voicemail,
    send_sms,
)
from app.scripts.templates import get_script
from app.core.config import settings

router = APIRouter(prefix="/webhook/call", tags=["webhooks"])


async def _get_call_and_script(call_id: int, db: AsyncSession):
    result = await db.execute(
        select(Call, Customer, Campaign)
        .join(Customer, Call.customer_id == Customer.id)
        .join(Campaign, Call.campaign_id == Campaign.id)
        .where(Call.id == call_id)
    )
    row = result.first()
    if not row:
        return None, None, None, None
    call, customer, campaign = row
    script = get_script(
        campaign.script_key,
        customer_name=customer.name.split()[0],  # first name only
        agent_name="Sarah",
        business_name=settings.BUSINESS_NAME,
        store_address=settings.STORE_ADDRESS,
        store_phone=settings.STORE_PHONE,
        store_website=settings.STORE_WEBSITE,
    )
    return call, customer, campaign, script


@router.post("/intro")
async def call_intro(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Entry point — plays the intro script and waits for keypress."""
    form = await request.form()
    answered_by = form.get("AnsweredBy", "human")

    call, customer, campaign, script = await _get_call_and_script(call_id, db)
    if not call:
        return PlainTextResponse("<Response><Hangup/></Response>", media_type="application/xml")

    # If voicemail detected, leave a message and hang up
    if answered_by in ("machine_start", "machine_end_beep", "machine_end_silence"):
        audio_url = await generate_and_cache(script["intro"], f"vm_{call_id}")
        await db.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(status=CallStatus.voicemail, outcome=CallOutcome.voicemail_left, started_at=datetime.now(timezone.utc))
        )
        await db.commit()
        return PlainTextResponse(twiml_voicemail(audio_url), media_type="application/xml")

    # Human answered — play intro and gather input
    await db.execute(
        update(Call)
        .where(Call.id == call_id)
        .values(status=CallStatus.in_progress, started_at=datetime.now(timezone.utc))
    )
    await db.commit()

    audio_url = await generate_and_cache(script["intro"], f"intro_{call_id}")
    action = f"{settings.APP_BASE_URL}/webhook/call/response?call_id={call_id}"
    return PlainTextResponse(
        twiml_play_gather(audio_url, action),
        media_type="application/xml",
    )


@router.post("/response")
async def call_response(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Handle keypress after intro."""
    form = await request.form()
    digit = form.get("Digits", "")
    no_input = request.query_params.get("no_input")

    call, customer, campaign, script = await _get_call_and_script(call_id, db)
    if not call:
        return PlainTextResponse("<Response><Hangup/></Response>", media_type="application/xml")

    if no_input or not digit:
        # No input — replay prompt once more then hang up
        audio_url = await generate_and_cache(script["no_input"], f"noinput_{call_id}")
        action = f"{settings.APP_BASE_URL}/webhook/call/final?call_id={call_id}"
        return PlainTextResponse(
            twiml_play_gather(audio_url, action),
            media_type="application/xml",
        )

    if digit == "1":
        # Interested — play more info
        audio_url = await generate_and_cache(script["more_info"], f"info_{call_id}")
        action = f"{settings.APP_BASE_URL}/webhook/call/followup?call_id={call_id}"
        return PlainTextResponse(
            twiml_play_gather(audio_url, action),
            media_type="application/xml",
        )

    elif digit == "2":
        # Callback requested
        audio_url = await generate_and_cache(script["callback"], f"cb_{call_id}")
        await db.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(outcome=CallOutcome.callback_requested, status=CallStatus.completed)
        )
        await db.commit()
        return PlainTextResponse(twiml_play_and_end(audio_url), media_type="application/xml")

    elif digit == "3":
        # Opt-out / DNC
        audio_url = await generate_and_cache(script["opt_out"], f"optout_{call_id}")
        await db.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(outcome=CallOutcome.not_interested, status=CallStatus.completed)
        )
        await db.execute(
            update(Customer)
            .where(Customer.id == call.customer_id)
            .values(do_not_call=True)
        )
        await db.commit()
        return PlainTextResponse(twiml_play_and_end(audio_url), media_type="application/xml")

    else:
        # Invalid key — treat as no input
        audio_url = await generate_and_cache(script["no_input"], f"noinput2_{call_id}")
        action = f"{settings.APP_BASE_URL}/webhook/call/final?call_id={call_id}"
        return PlainTextResponse(
            twiml_play_gather(audio_url, action),
            media_type="application/xml",
        )


@router.post("/followup")
async def call_followup(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Handle keypress after 'more info' — SMS or transfer to human."""
    form = await request.form()
    digit = form.get("Digits", "")

    call, customer, campaign, script = await _get_call_and_script(call_id, db)
    if not call:
        return PlainTextResponse("<Response><Hangup/></Response>", media_type="application/xml")

    result = await db.execute(select(Customer).where(Customer.id == call.customer_id))
    customer_row = result.scalar_one_or_none()

    if digit == "1":
        # Send SMS with store details
        if customer_row:
            sms_body = (
                f"Hi {customer_row.name.split()[0]}! Here are our details:\n"
                f"{settings.BUSINESS_NAME}\n"
                f"{settings.STORE_ADDRESS}\n"
                f"Tel: {settings.STORE_PHONE}\n"
                f"Web: {settings.STORE_WEBSITE}\n\n"
                f"Don't miss our sale — limited time only!"
            )
            send_sms(customer_row.phone, sms_body)
        audio_url = await generate_and_cache(script["sms_confirm"], f"sms_{call_id}")
        await db.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(outcome=CallOutcome.interested, status=CallStatus.completed)
        )
        await db.commit()
        return PlainTextResponse(twiml_play_and_end(audio_url), media_type="application/xml")

    elif digit == "2":
        # Transfer to human agent
        audio_url = await generate_and_cache(script["transfer"], f"transfer_{call_id}")
        await db.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(outcome=CallOutcome.transferred, status=CallStatus.completed)
        )
        await db.commit()
        return PlainTextResponse(
            twiml_transfer(audio_url, settings.STORE_PHONE),
            media_type="application/xml",
        )

    elif digit == "9":
        # Goodbye
        audio_url = await generate_and_cache(script["goodbye"], f"bye_{call_id}")
        await db.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(outcome=CallOutcome.not_interested, status=CallStatus.completed)
        )
        await db.commit()
        return PlainTextResponse(twiml_play_and_end(audio_url), media_type="application/xml")

    else:
        audio_url = await generate_and_cache(script["goodbye"], f"bye2_{call_id}")
        return PlainTextResponse(twiml_play_and_end(audio_url), media_type="application/xml")


@router.post("/final")
async def call_final(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Final fallback — no response after second prompt, hang up."""
    call, customer, campaign, script = await _get_call_and_script(call_id, db)
    audio_url = await generate_and_cache(script["goodbye"], f"final_{call_id}")
    await db.execute(
        update(Call)
        .where(Call.id == call_id)
        .values(status=CallStatus.completed)
    )
    await db.commit()
    return PlainTextResponse(twiml_play_and_end(audio_url), media_type="application/xml")


@router.post("/status")
async def call_status(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Twilio status callback — updates call record with final status and duration."""
    form = await request.form()
    call_status = form.get("CallStatus", "")
    duration = form.get("CallDuration", 0)

    status_map = {
        "completed": CallStatus.completed,
        "no-answer": CallStatus.no_answer,
        "busy": CallStatus.no_answer,
        "failed": CallStatus.failed,
        "canceled": CallStatus.failed,
    }
    db_status = status_map.get(call_status, CallStatus.completed)

    await db.execute(
        update(Call)
        .where(Call.id == call_id)
        .values(
            status=db_status,
            duration_seconds=int(duration),
            ended_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    return PlainTextResponse("OK")
