#!/usr/bin/env python3
"""
vapi_call.py — place a live outbound AI sales call via Vapi.ai.

No ngrok. No Twilio. Vapi handles the phone call entirely in the cloud.

Setup (one time, ~5 min):
  1. Sign up free at app.vapi.ai — you get $10 in free credits.
  2. Dashboard → Phone Numbers → Buy Number (US number, free tier supported).
  3. Copy the Phone Number ID → .env as VAPI_PHONE_NUMBER_ID
  4. Dashboard → API Keys → copy → .env as VAPI_API_KEY

Usage:
  python vapi_call.py "+1 628 555 0100" "Jordan"
"""

import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
from app.core.business_config import business_config  # noqa: E402

VAPI_KEY        = os.getenv("VAPI_API_KEY", "")
PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID", "")
AGENT_NAME      = business_config.agent_name
BUSINESS_NAME   = business_config.business_name
BASE            = "https://api.vapi.ai"

_promo = business_config.promotion
_offer_fact = f"- Current offer: {_promo.headline}. {_promo.details}".strip() if (_promo.active and _promo.headline) else "- No active promotion — speak generally about our services."
_label = business_config.booking.appointment_label

SYSTEM_PROMPT = f"""\
You are {AGENT_NAME}, an AI assistant making an outbound call on behalf of \
{BUSINESS_NAME}, a {business_config.industry}. You are calling a customer or past \
customer. Speak only what should be said out loud — nothing else.

THE ONLY FACTS YOU MAY STATE
{_offer_fact}
- The customer can book a {_label}.
- You are calling on behalf of {BUSINESS_NAME}.

DO NOT INVENT
- No specific prices or dollar figures beyond what's listed above.
- No financing, deposits, or payment plans not listed above.
- No product brands, stock levels, staffing, or timelines you don't actually know.
- No extra promotions or discounts beyond what's listed above.
- No terms or conditions not listed above.
If asked about pricing, say: "It depends on your specific needs — that's exactly \
what the {_label} is for. Someone will be able to give you an exact answer, no obligation."

RESPECT THE CUSTOMER
- "Remove me / don't call again" → stop selling immediately, apologize once, confirm removed.
- "Are you AI?" → "Yes, I'm an AI assistant calling on behalf of {BUSINESS_NAME}."
- Bad timing → offer a callback, don't push.
- "Not interested" → accept gracefully, thank them, let them go.

HOW TO TALK
- 1–2 sentences per turn, ONE question then listen. This is a phone call, not a pitch.
- Match their energy. Sound like a real person, not a script.
- Use their first name at most once or twice.
"""


def _headers() -> dict:
    return {"Authorization": f"Bearer {VAPI_KEY}", "Content-Type": "application/json"}


def create_assistant(client: httpx.Client, customer_name: str) -> str:
    promo_hook = (
        f"We've got {_promo.headline.lower()} and I wanted to give you a heads up. "
        if (_promo.active and _promo.headline) else ""
    )
    first_message = (
        f"Hi{' ' + customer_name if customer_name != 'there' else ''}! "
        f"This is {AGENT_NAME} calling on behalf of {BUSINESS_NAME}. "
        f"{promo_hook}"
        f"Do you have a quick moment?"
    )
    payload = {
        "name": f"{AGENT_NAME} — {BUSINESS_NAME}",
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "systemPrompt": SYSTEM_PROMPT,
            "maxTokens": 200,
        },
        "voice": {
            "provider": "openai",
            "voiceId": "nova",
        },
        "firstMessage": first_message,
        "startSpeakingPlan": {"waitSeconds": 2},
        "endCallMessage": "Thanks so much for your time. Have a great day!",
        "endCallPhrases": ["goodbye", "bye", "not interested", "take care", "no thanks"],
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "en",
        },
    }
    resp = client.post(f"{BASE}/assistant", headers=_headers(), json=payload, timeout=30)
    if not resp.is_success:
        print(f"[error] Create assistant: {resp.status_code} — {resp.text}")
        sys.exit(1)
    return resp.json()["id"]


def start_call(client: httpx.Client, assistant_id: str, to_number: str) -> str:
    resp = client.post(f"{BASE}/call", headers=_headers(), json={
        "assistantId": assistant_id,
        "phoneNumberId": PHONE_NUMBER_ID,
        "customer": {"number": to_number},
    }, timeout=30)
    if not resp.is_success:
        print(f"[error] Start call: {resp.status_code} — {resp.text}")
        sys.exit(1)
    return resp.json()["id"]


def watch(client: httpx.Client, call_id: str):
    print(f"\nLive transcript\n{'─' * 60}")
    seen = 0
    while True:
        time.sleep(2)
        try:
            data = client.get(f"{BASE}/call/{call_id}", headers=_headers(), timeout=15).json()
        except Exception:
            continue

        status   = data.get("status", "unknown")
        messages = (data.get("artifact") or {}).get("messages") or data.get("messages") or []

        for msg in messages[seen:]:
            role    = msg.get("role", "?")
            content = msg.get("message") or msg.get("content") or ""
            if content:
                label = f"{AGENT_NAME}:" if role == "assistant" else "Customer:"
                print(f"\n{label} {content}")
        seen = len(messages)

        if status in ("ended", "failed"):
            print(f"\n{'─' * 60}\nCall {status}.")
            summary = (data.get("artifact") or {}).get("summary")
            if summary:
                print(f"Summary: {summary}")
            print(f"Full log → app.vapi.ai → Calls → {call_id}")
            break

        print(f"\r  [{status}...]   ", end="", flush=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python vapi_call.py \"+1 628 555 0100\" \"Jordan\"")
        sys.exit(1)

    to_number     = sys.argv[1]
    customer_name = sys.argv[2] if len(sys.argv) > 2 else "there"

    missing = [k for k, v in [("VAPI_API_KEY", VAPI_KEY), ("VAPI_PHONE_NUMBER_ID", PHONE_NUMBER_ID)] if not v]
    if missing:
        print(f"Missing in .env: {', '.join(missing)}")
        sys.exit(1)

    with httpx.Client() as client:
        print(f"Building assistant for {BUSINESS_NAME}...")
        aid = create_assistant(client, customer_name)
        print(f"Dialling {to_number}...")
        call_id = start_call(client, aid, to_number)
        print(f"Call placed — ringing...")
        watch(client, call_id)


if __name__ == "__main__":
    main()
