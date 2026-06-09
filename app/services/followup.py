"""
Follow-up service — schedules and sends SMS follow-ups after calls.

Pairing a call with an SMS materially lifts conversion, so every no-answer,
voicemail, and "interested" call queues an appropriate text.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FollowUp, FollowUpType, FollowUpStatus, Customer, CallOutcome
from app.services.caller import send_sms
from app.core.config import settings


def _deal_blurb() -> str:
    return (
        f"{settings.BUSINESS_NAME} — don't miss our current sale! "
        f"Visit us at {settings.STORE_ADDRESS} or {settings.STORE_WEBSITE}. "
        f"Call {settings.STORE_PHONE} for details."
    )


async def schedule_sms(
    db: AsyncSession,
    customer_id: int,
    call_id: int | None,
    body: str,
    delay_minutes: int = 2,
):
    """Queue an SMS to be sent shortly after a call ends."""
    fu = FollowUp(
        customer_id=customer_id,
        call_id=call_id,
        type=FollowUpType.sms,
        message=body,
        scheduled_at=datetime.now(timezone.utc) + timedelta(minutes=delay_minutes),
    )
    db.add(fu)
    await db.commit()
    return fu


async def schedule_followup_for_outcome(
    db: AsyncSession, customer_id: int, call_id: int, outcome: CallOutcome, first_name: str
):
    """Pick the right SMS based on how the call went, and queue it."""
    blurb = _deal_blurb()
    messages = {
        CallOutcome.no_answer: (
            f"Hi {first_name}, we tried to reach you about a special offer! {blurb}"
        ),
        CallOutcome.voicemail_left: (
            f"Hi {first_name}, we left you a voicemail about our sale. {blurb}"
        ),
        CallOutcome.interested: (
            f"Thanks for your interest, {first_name}! As promised: {blurb}"
        ),
        CallOutcome.callback_requested: (
            f"Hi {first_name}, we'll call you back soon. In the meantime: {blurb}"
        ),
    }
    body = messages.get(outcome)
    if body:
        await schedule_sms(db, customer_id, call_id, body)


async def process_pending_followups(db: AsyncSession) -> int:
    """
    Worker tick: send all SMS follow-ups whose scheduled_at has passed.
    Returns the number sent. Called periodically by the scheduler.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(FollowUp, Customer)
        .join(Customer, FollowUp.customer_id == Customer.id)
        .where(
            FollowUp.status == FollowUpStatus.pending,
            FollowUp.type == FollowUpType.sms,
            FollowUp.scheduled_at <= now,
        )
        .limit(100)
    )
    rows = result.all()

    sent = 0
    for fu, customer in rows:
        if customer.do_not_call:
            fu.status = FollowUpStatus.cancelled
            continue
        try:
            send_sms(customer.phone, fu.message)
            fu.status = FollowUpStatus.sent
            fu.sent_at = now
            sent += 1
        except Exception:
            fu.status = FollowUpStatus.failed
    await db.commit()
    return sent
