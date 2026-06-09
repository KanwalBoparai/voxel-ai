"""
Background scheduler — runs recurring jobs without manual intervention:
  • every minute: send any due SMS follow-ups
The scheduler respects calling hours implicitly because SMS is allowed anytime,
but call-dispatch jobs check is_within_calling_hours() before dialing.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.database import AsyncSessionLocal
from app.services.followup import process_pending_followups

scheduler = AsyncIOScheduler()


async def _followup_tick():
    async with AsyncSessionLocal() as db:
        sent = await process_pending_followups(db)
        if sent:
            print(f"[scheduler] sent {sent} follow-up SMS")


def start_scheduler():
    scheduler.add_job(_followup_tick, "interval", minutes=1, id="followup_tick", replace_existing=True)
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
