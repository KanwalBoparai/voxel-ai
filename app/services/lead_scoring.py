"""
Lead scoring — turns call behavior into a 0-100 score so the store can
prioritize the hottest prospects for human follow-up.
"""
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Customer, Call, CallOutcome

# Points awarded per outcome
OUTCOME_POINTS = {
    CallOutcome.appointment_booked: 50,
    CallOutcome.transferred: 40,
    CallOutcome.interested: 30,
    CallOutcome.callback_requested: 20,
    CallOutcome.voicemail_left: 5,
    CallOutcome.no_answer: 0,
    CallOutcome.not_interested: -10,
}

HOT_LEAD_THRESHOLD = 40


def score_for_call(outcome: CallOutcome | None, duration_seconds: int | None) -> int:
    """Compute an interest score for a single call."""
    score = OUTCOME_POINTS.get(outcome, 0)
    # Longer engaged calls signal genuine interest
    if duration_seconds:
        if duration_seconds > 90:
            score += 15
        elif duration_seconds > 45:
            score += 8
    return max(0, min(100, score))


async def update_customer_score(db: AsyncSession, customer_id: int):
    """Recompute a customer's rolling lead score from their best recent call."""
    result = await db.execute(
        select(Call).where(Call.customer_id == customer_id)
    )
    calls = result.scalars().all()
    if not calls:
        return

    best = max((score_for_call(c.outcome, c.duration_seconds) for c in calls), default=0)

    tags_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = tags_result.scalar_one_or_none()
    if not customer:
        return

    tags = set(customer.tags or [])
    if best >= HOT_LEAD_THRESHOLD:
        tags.add("hot_lead")
    else:
        tags.discard("hot_lead")

    await db.execute(
        update(Customer)
        .where(Customer.id == customer_id)
        .values(lead_score=best, tags=list(tags), last_contacted_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def get_hot_leads(db: AsyncSession, limit: int = 50):
    """Return customers most worth a human follow-up call."""
    result = await db.execute(
        select(Customer)
        .where(Customer.lead_score >= HOT_LEAD_THRESHOLD, Customer.do_not_call == False)
        .order_by(Customer.lead_score.desc())
        .limit(limit)
    )
    return result.scalars().all()
