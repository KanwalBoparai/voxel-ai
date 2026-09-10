"""
Business configuration — the one place that makes the agent "yours".

Every business-specific detail (name, industry, services, hours, FAQs, tone,
booking rules) lives in a JSON file instead of Python source. Swap the file
(or edit it from the dashboard's AI Settings page) and the same code runs a
dental clinic, a law firm, a restaurant, or anything else — no redeploy of
application code required.

Set BUSINESS_CONFIG_PATH to point at a different file (see config/examples/
for industry starting points). Defaults to config/business.json.
"""
import json
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from app.core.config import settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "business.json"

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class DayHours(BaseModel):
    open: str = "09:00"
    close: str = "17:00"
    closed: bool = False


class Service(BaseModel):
    name: str
    description: str = ""


class FAQ(BaseModel):
    question: str
    answer: str


class Promotion(BaseModel):
    active: bool = False
    headline: str = ""
    details: str = ""


class Booking(BaseModel):
    # What the appointment is called when the agent speaks about it out loud.
    appointment_label: str = "appointment"
    duration_minutes: int = 30
    requires_address: bool = False
    location_type: str = "in_office"  # in_office | in_home | virtual
    scheduling_link: str = ""


class BusinessConfig(BaseModel):
    business_name: str = "Your Business"
    industry: str = "general business"
    tagline: str = ""
    agent_name: str = "Ava"
    owner_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    website: str = ""
    timezone: str = "America/Toronto"
    tone: str = "warm, professional, and concise"
    greeting_style: str = "friendly and brief"
    services: list[Service] = Field(default_factory=list)
    faqs: list[FAQ] = Field(default_factory=list)
    promotion: Promotion = Field(default_factory=Promotion)
    booking: Booking = Field(default_factory=Booking)
    hours: dict[str, DayHours] = Field(
        default_factory=lambda: {day: DayHours() for day in _WEEKDAYS}
    )

    def hours_summary(self) -> str:
        lines = []
        for day in _WEEKDAYS:
            d = self.hours.get(day, DayHours(closed=True))
            label = day.capitalize()
            lines.append(f"{label}: Closed" if d.closed else f"{label}: {d.open}–{d.close}")
        return "; ".join(lines)

    def services_summary(self) -> str:
        if not self.services:
            return "General services (no specific list configured)"
        return "; ".join(f"{s.name} — {s.description}" if s.description else s.name for s in self.services)

    def faqs_summary(self) -> str:
        if not self.faqs:
            return "(none configured)"
        return "\n".join(f"Q: {f.question}\nA: {f.answer}" for f in self.faqs)


def config_path() -> Path:
    override = settings.BUSINESS_CONFIG_PATH
    return Path(override) if override else DEFAULT_CONFIG_PATH


def load_business_config(path: Optional[Path] = None) -> BusinessConfig:
    p = path or config_path()
    if not p.exists():
        return BusinessConfig()
    with open(p, "r") as f:
        data = json.load(f)
    return BusinessConfig(**data)


# Loaded once at import time from the committed JSON file. This is the
# baseline; anything the dashboard has saved is layered on top from the
# database by refresh_business_config().
business_config = load_business_config()


# ── database overlay ─────────────────────────────────────────────────────────
#
# The dashboard used to write config/business.json directly. That works on a
# normal server but not on a serverless host, where the deployment directory is
# read-only and the write raises OSError. Saved edits go to the settings table
# instead, keyed by _DB_KEY.

_DB_KEY = "business_config"

# How long a warm container may serve its in-memory copy before re-reading the
# database. Bounds how stale another container's view can be after a save.
_REFRESH_SECONDS = 60
_last_refresh: Optional[float] = None


def _apply(config: BusinessConfig) -> BusinessConfig:
    """
    Update business_config in place — mutating the existing instance rather
    than rebinding the name — so every module that already did
    `from app.core.business_config import business_config` sees the change.
    """
    business_config.__dict__.update(config.__dict__)
    return business_config


async def load_business_config_from_db() -> BusinessConfig:
    """Overlay the dashboard-saved config, if any, onto the in-memory singleton."""
    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal, ensure_schema
    from app.db.models import Setting

    # This runs from middleware, which can be the very first thing to touch the
    # database — ahead of any request that goes through get_db().
    await ensure_schema()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting.value).where(Setting.key == _DB_KEY))
        data = result.scalar_one_or_none()

    return _apply(BusinessConfig(**data)) if data else business_config


async def save_business_config_to_db(config: BusinessConfig) -> BusinessConfig:
    """Persist a dashboard edit and apply it to this container immediately."""
    from app.db.database import AsyncSessionLocal
    from app.db.models import Setting

    async with AsyncSessionLocal() as db:
        await db.merge(Setting(key=_DB_KEY, value=config.model_dump(mode="json")))
        await db.commit()

    global _last_refresh
    _last_refresh = time.monotonic()
    return _apply(config)


async def refresh_business_config() -> BusinessConfig:
    """
    Re-read the saved config if this container's copy has gone stale.

    Called per request from main.py. A database that is unreachable or has no
    settings table yet must not take the whole app down, so failures fall back
    to the committed baseline and are rate-limited like a success.
    """
    global _last_refresh
    now = time.monotonic()
    if _last_refresh is not None and now - _last_refresh < _REFRESH_SECONDS:
        return business_config

    _last_refresh = now
    try:
        return await load_business_config_from_db()
    except Exception as exc:
        print(f"[business-config] using committed baseline; DB read failed: {exc}")
        return business_config
