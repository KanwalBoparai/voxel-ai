"""
The config-driven design is Voxel's core claim — one codebase serves any
business vertical through config/business.json — so these cover the schema that
drives every deployment, and the phone normalisation that backs do-not-call
handling.
"""
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "business.json"
EXAMPLES_DIR = REPO_ROOT / "config" / "examples"


def test_business_config_file_exists():
    assert CONFIG_PATH.exists(), "config/business.json is required to boot the agent"


def test_business_config_is_valid_json():
    json.loads(CONFIG_PATH.read_text())


def test_business_config_validates_against_schema():
    from app.core.business_config import load_business_config

    config = load_business_config(CONFIG_PATH)
    assert config.business_name
    assert config.agent_name
    assert config.booking.duration_minutes > 0


@pytest.mark.parametrize(
    "example", sorted(EXAMPLES_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_every_shipped_example_validates(example):
    """Each example is a supported starting point, so a broken one is a bug."""
    from app.core.business_config import load_business_config

    config = load_business_config(example)
    assert config.business_name
    assert config.hours, "an agent with no hours can't answer 'when are you open?'"


def test_summaries_render_without_a_configured_business():
    """
    The defaults have to produce usable prompt text on their own — they are what
    a fresh clone runs on before anyone edits the config.
    """
    from app.core.business_config import BusinessConfig

    blank = BusinessConfig()
    assert "Monday" in blank.hours_summary()
    assert blank.services_summary()
    assert blank.faqs_summary()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("416-555-0142", "+14165550142"),
        ("+1 416 555 0142", "+14165550142"),
        ("(416) 555-0142", "+14165550142"),
    ],
)
def test_phone_numbers_normalise_to_e164(raw, expected):
    """E.164 normalisation is what makes do-not-call matching reliable."""
    import phonenumbers

    parsed = phonenumbers.parse(raw, "CA")
    assert phonenumbers.is_valid_number(parsed)
    assert phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.E164
    ) == expected


def test_unconfigured_calendar_degrades_instead_of_raising():
    """
    With no Google credentials the booking tool must return a note the agent can
    say out loud, not raise — an exception mid-call drops the conversation.
    """
    import asyncio

    from app.services.google_calendar import check_available_slots

    result = asyncio.run(check_available_slots("Tuesday", "afternoon"))
    assert result["available_slots"] == []
    assert "note" in result or "error" in result
