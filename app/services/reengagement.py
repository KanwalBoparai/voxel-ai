"""
Re-engagement — automatically finds lapsed customers (no purchase in N days)
and queues them into a campaign so the store keeps wallets warm.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Customer

DEFAULT_LAPSE_DAYS = 90


async def find_lapsed_customers(db: AsyncSession, lapse_days: int = DEFAULT_LAPSE_DAYS):
    """
    Customers who either never purchased or whose last purchase is older
    than `lapse_days`, and who are still callable.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lapse_days)
    result = await db.execute(
        select(Customer).where(
            Customer.do_not_call == False,
            (Customer.last_purchase_at == None) | (Customer.last_purchase_at < cutoff),
        )
    )
    customers = result.scalars().all()
    # Tag them so they show up in reporting
    for c in customers:
        tags = set(c.tags or [])
        tags.add("lapsed")
        c.tags = list(tags)
    await db.commit()
    return customers
