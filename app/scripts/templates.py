"""
Call script templates for the keypad (DTMF) outbound flow (app/api/webhooks.py).

This is the simpler, legacy call flow — press 1/2/3 instead of a live
conversation. The script is generated from the business config (name, promotion,
services, address) instead of being hardcoded per-business, so any business can
use it by editing config/business.json.
"""
from app.core.business_config import business_config


def _default_script() -> dict:
    biz = business_config.business_name
    agent = business_config.agent_name
    promo = business_config.promotion
    address = business_config.address or "our location"

    if promo.active and promo.headline:
        offer_line = f"I'm reaching out because {promo.headline.lower()}. "
    else:
        offer_line = "I'm reaching out to share what's new with us. "

    return {
        "intro": (
            "Hello, may I speak with {customer_name}? "
            f"Hi {{customer_name}}! This is {agent} calling from {biz}. "
            "I hope I'm not catching you at a bad time. "
            f"{offer_line}"
            "Press 1 to hear more, "
            "press 2 if you'd like us to call you at a better time, "
            "or press 3 to be removed from our call list."
        ),
        "more_info": (
            f"{promo.details or 'We would love to help you out.'} "
            f"You can find us at {address}. "
            "Press 1 to get our details by text, "
            "press 2 to speak with someone on our team right now, "
            "press 3 to book a visit, "
            "or press 9 to end this call."
        ),
        "book_confirm": (
            "Perfect! We've booked your visit and we'll text you the details. "
            "We can't wait to help you, {customer_name}! Goodbye."
        ),
        "callback": (
            "No problem at all! We'll give you a call back at a more convenient time. "
            "Thank you for your time, {customer_name}, and have a wonderful day!"
        ),
        "opt_out": (
            "I completely understand. We'll remove you from our call list right away. "
            "Thank you for your time, {customer_name}, and have a great day!"
        ),
        "sms_confirm": (
            "Great! We'll send our details to this number right away. "
            "We look forward to hearing from you, {customer_name}! Goodbye."
        ),
        "transfer": (
            "Wonderful! Please hold for just a moment while I connect you with someone from our team. "
            "They'll be happy to answer all your questions!"
        ),
        "no_input": (
            "I'm sorry, I didn't catch that. "
            "Press 1 to hear more, press 2 for a callback, or press 9 to end this call."
        ),
        "goodbye": (
            "Thank you for your time, {customer_name}. Have a wonderful day! Goodbye."
        ),
    }


# script_key is kept for backward compatibility with existing campaigns/tests —
# every key currently resolves to the same config-driven script.
SCRIPTS = {"default": _default_script()}


def get_script(script_key: str, **kwargs) -> dict:
    template = SCRIPTS.get(script_key) or SCRIPTS["default"]
    return {k: v.format(**kwargs) for k, v in template.items()}
