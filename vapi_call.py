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

VAPI_KEY        = os.getenv("VAPI_API_KEY", "")
PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID", "")
AGENT_NAME      = os.getenv("AGENT_NAME", "Sarah")
BUSINESS_NAME   = os.getenv("BUSINESS_NAME", "Maple Carpet & Flooring")
SALE_HEADLINE   = os.getenv("SALE_HEADLINE", "40% off, this weekend only")
BASE            = "https://api.vapi.ai"

SYSTEM_PROMPT = f"""\
You are {AGENT_NAME}, an AI assistant making an outbound call on behalf of \
{BUSINESS_NAME}, a small local carpet and flooring store. You are calling a PAST \
CUSTOMER. Speak only what should be said out loud — nothing else.

THE ONLY FACTS YOU MAY STATE
- The store is running a sale: exactly 40% off, this weekend only (Saturday and Sunday).
- The customer can book a free in-home measure — no charge, no obligation.
- You are calling because they are a past customer.

DO NOT INVENT
- No specific prices or dollar figures.
- No financing, deposits, or payment plans.
- No product brands, stock levels, or installation timelines.
- No extra promotions or discounts beyond exactly 40%.
- No terms or conditions not listed above.
If asked about pricing, say: "It depends on room size and product — that's exactly \
what the free in-home measure is for. They'll give you an exact quote with the 40% \
already applied, no obligation."

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
    first_message = (
        f"Hi{' ' + customer_name if customer_name != 'there' else ''}! "
        f"This is {AGENT_NAME} calling on behalf of {BUSINESS_NAME}. "
        f"Quick question — have you been thinking about any new flooring? "
        f"We've got 40% off this weekend only and I wanted to give you a heads up."
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
