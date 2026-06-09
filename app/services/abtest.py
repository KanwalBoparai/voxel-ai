"""
A/B testing engine for call scripts.

A campaign can define `script_variants` (a list of script keys). Each call is
randomly assigned one variant so we can measure which message converts best.
"""
import random
from app.db.models import Campaign


def pick_variant(campaign: Campaign) -> str:
    """Return a script key for this call, splitting traffic across variants."""
    variants = campaign.script_variants or []
    if not variants:
        return campaign.script_key  # no A/B test configured — use default
    return random.choice(variants)


def conversion_rate(interested: int, total: int) -> float:
    """Percentage of answered calls that showed interest."""
    if total == 0:
        return 0.0
    return round((interested / total) * 100, 1)
