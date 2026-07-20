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


def save_business_config(config: BusinessConfig, path: Optional[Path] = None) -> None:
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(config.model_dump(), f, indent=2)


# Loaded once at import time; reload_business_config() refreshes it (used by
# the AI Settings dashboard page after a save).
business_config = load_business_config()


def reload_business_config() -> BusinessConfig:
    """
    Refresh business_config in place (mutating the existing instance's fields
    rather than rebinding the name) so every module that already did
    `from app.core.business_config import business_config` sees the update
    immediately — no process restart needed after a dashboard save.
    """
    fresh = load_business_config()
    business_config.__dict__.update(fresh.__dict__)
    return business_config
