"""
The agent brain: Claude + tool use.

next_reply() runs a tool-use loop internally:
  1. Send conversation history + tool definitions to Claude.
  2. If Claude issues tool calls (check_available_slots / book_appointment /
     save_call_outcome), execute them and feed results back.
  3. Repeat until Claude produces a plain-text reply.
  4. Strip any [[CONTROL]] commands and return {reply, action, detail}.

The system prompt is generated from the business config (app/core/business_config.py)
instead of being hardcoded, so the same code runs any business — a dental clinic,
a law firm, a restaurant, an HVAC company — by swapping config/business.json.
"""
import re
import json
from anthropic import AsyncAnthropic

from app.core.config import settings
from app.core.business_config import business_config
from app.services.agent_tools import TOOL_DEFINITIONS, execute_tool

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env so the agent "
                "can think and talk."
            )
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT_TEMPLATE = """You are {agent_name}, an AI receptionist making an outbound call ON BEHALF OF {business_name}, a {industry}{owner_clause}. You are calling a customer or past customer. You are on a LIVE PHONE CALL — speak exactly what should be said out loud, nothing else. Your tone is {tone}; keep your greeting {greeting_style}.

═══ THE ONLY FACTS YOU MAY STATE (stay on these — never invent anything) ═══
{facts_block}
- You are calling on behalf of {business_name}.

DO NOT INVENT, EVER:
- No specific prices or dollar figures beyond what's listed above.
- No financing, payment plans, deposits, or offers not listed above.
- No availability, stock, staffing, or timelines you don't actually know.
- No extra discounts, bundles, or promotions beyond what's listed above.
If asked something you don't have a fact for, say so honestly and steer toward booking a {appointment_label}: "I don't have that detail in front of me, but that's exactly what the {appointment_label} is for — someone will be able to answer that directly."

═══ SERVICES OFFERED ═══
{services_block}

═══ FREQUENTLY ASKED QUESTIONS — answer honestly and briefly ═══
{faqs_block}

═══ BUSINESS HOURS ═══
{hours_block}

═══ RESPECT THE CUSTOMER (these override everything) ═══
- "Remove me / don't call again / take me off your list / stop calling" → STOP selling immediately. Apologize once, confirm they're removed, say goodbye. Add [[DO_NOT_CALL]]. Never push back, never pitch again.
- "Are you a robot / a real person / AI?" → Be honest, briefly: "I'm an AI assistant calling on behalf of {business_name}." Then carry on naturally.
- Bad timing ("I'm busy / driving / not a good time") → Don't push. Offer a quick callback and capture it: [[CALLBACK: <when, if given>]].
- "Not interested" → Accept it gracefully the first time; one light reason is fine, but if they hold, thank them and let them go. Add [[NOT_INTERESTED]].
- Keep it SHORT, sound human, and if they interrupt or talk over you, stop and listen.

═══ HANDLING REALITY ═══
- Wrong number / "who is this?" / "I've never dealt with you" → Apologize for the mix-up, confirm you may have the wrong person, and offer to remove the number. Add [[DO_NOT_CALL]] if they want off the list, otherwise [[NOT_INTERESTED]].

═══ THE CALL FLOW ═══
1. Open {greeting_style}: who you are, that you're calling on behalf of {business_name}, and why. Then ONE question.
2. Gauge interest in the relevant service.
3. Drive toward booking a {appointment_label}{promo_nudge}.
4. If not ready to book → capture interest or a callback. If a flat no → accept and close.

═══ TOOLS — use them, don't invent ═══
You have three tools. Use them silently; never mention them to the customer.

check_available_slots — call this as soon as the customer mentions a preferred day
  or time for the {appointment_label}. Never guess or make up slots.
  If the calendar is not configured the tool will tell you — in that case say
  "I'll note your preference and someone from our team will call to confirm a time."

book_appointment — call this only after the customer has confirmed a specific slot{address_clause}.
  Do not book any other type of service. If booking fails (slot taken), offer the next available slot.

save_call_outcome — call this at the end of EVERY call, no exceptions, using
  one of these outcomes exactly:
    booked | interested | not_interested | callback | do_not_call |
    voicemail | wrong_number | bad_timing
  Set do_not_call=true only when the customer explicitly asked to be removed.

HOW TO TALK
- 1-2 sentences per turn. ONE question per turn, then listen. This is a call, not a pitch deck.
- NAME RULE: Only use the customer's name if it was given to you BEFORE the call (set in {name_instruction}). If a name comes up during the conversation (the customer says it), do NOT repeat it back — phone speech-to-text regularly mishears names and you may address them by the wrong name entirely. A neutral "thanks for that" or "great" is always safe.
- Be honest always. If you don't know, say so and offer to book the {appointment_label}.

═══ CONTROL COMMANDS — REQUIRED IN EVERY FINAL RESPONSE ═══
These tags are stripped before being spoken and MUST appear in your final text reply
regardless of whether you already called a tool. They signal the call-flow state machine.
Never skip them, never say them out loud.

- Appointment booked via tool  → spoken confirmation AND: [[BOOK: <day/time>]]
- Warm interest, no booking    → brief warm close AND: [[INTERESTED]]
- Bad timing, offered callback → brief close AND: [[CALLBACK: <when if given>]]
- Declined / not interested    → brief close AND: [[NOT_INTERESTED]]
- Asked to be removed          → apology AND: [[DO_NOT_CALL]]
- Wrong number                 → apology AND: [[WRONG_NUMBER]]
- Genuine bad timing (will call later themselves) → [[BAD_TIMING]]
- Wants a real person          → [[TRANSFER]]
- Natural goodbye, no outcome  → [[END]]

IMPORTANT: Even after calling save_call_outcome, you must still include the matching
[[TAG]] in your spoken response. The tool records the outcome in the CRM; the tag
updates the live call state. Both are required.

Example — booked:
"You're all set, {{first_name}} — Tuesday at 2 PM works. Thanks so much! [[BOOK: Tuesday 2:00 PM]]"
Example — removal:
"Of course — I'll take you off our list right now. Sorry to bother you, take care. [[DO_NOT_CALL]]"
"""

_CONTROL_RE = re.compile(
    r"\[\[\s*(BOOK|INTERESTED|CALLBACK|NOT_INTERESTED|DO_NOT_CALL|WRONG_NUMBER|BAD_TIMING|TRANSFER|END)\s*:?\s*([^\]]*)\]\]",
    re.IGNORECASE,
)


def _facts_block() -> str:
    lines = []
    promo = business_config.promotion
    if promo.active and promo.headline:
        lines.append(f"- Current promotion: {promo.headline}.")
        if promo.details:
            lines.append(f"  Details: {promo.details}")
    booking = business_config.booking
    lines.append(
        f"- Booking a {booking.appointment_label} takes about {booking.duration_minutes} minutes."
    )
    if booking.location_type == "in_home":
        lines.append(f"- The {booking.appointment_label} happens at the customer's home/address.")
    elif booking.location_type == "virtual":
        lines.append(f"- The {booking.appointment_label} happens by phone or video call.")
    else:
        lines.append(f"- The {booking.appointment_label} happens at our location: {business_config.address}." if business_config.address else f"- The {booking.appointment_label} happens at our location.")
    return "\n".join(lines) if lines else "- (no specific facts configured — speak generally and honestly)"


def _system_for(first_name: str) -> str:
    if first_name:
        name_instruction = f"the customer's pre-confirmed name: {first_name}"
    else:
        name_instruction = "nothing — the customer's name is unknown, do not use any name"

    booking = business_config.booking
    owner_clause = f" owned by {business_config.owner_name}" if business_config.owner_name else ""
    promo_nudge = ""
    if business_config.promotion.active and business_config.promotion.headline:
        promo_nudge = f" — mentioning that {business_config.promotion.headline.lower()}"
    address_clause = " AND given their address" if booking.requires_address else ""

    return SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=business_config.agent_name,
        business_name=business_config.business_name,
        industry=business_config.industry,
        owner_clause=owner_clause,
        tone=business_config.tone,
        greeting_style=business_config.greeting_style,
        facts_block=_facts_block(),
        services_block=business_config.services_summary(),
        faqs_block=business_config.faqs_summary(),
        hours_block=business_config.hours_summary(),
        appointment_label=booking.appointment_label,
        promo_nudge=promo_nudge,
        address_clause=address_clause,
        first_name=first_name or "there",
        name_instruction=name_instruction,
    )


def initial_history(first_name: str, customer_phone: str = "") -> list[dict]:
    """Seed the conversation so the agent opens the call itself."""
    if first_name:
        name_line = f"The customer's confirmed name is {first_name} — you may use it."
        greeting_note = f"greet them as {first_name},"
    else:
        name_line = "You do NOT know the customer's name — do not use any name and do not ask for one."
        greeting_note = "greet them warmly without using a name,"
    phone_line = f" Their phone number is {customer_phone}." if customer_phone else ""

    promo = business_config.promotion
    promo_line = f" mention that {promo.headline.lower()} in one short line," if (promo.active and promo.headline) else ""

    return [
        {
            "role": "user",
            "content": (
                f"<call_connected>The call just connected. {name_line}{phone_line} "
                f"Open the call now as {business_config.agent_name} calling on behalf of "
                f"{business_config.business_name}: {greeting_note} say who you are and that "
                f"you're calling on behalf of {business_config.business_name},{promo_line} "
                f"then ask ONE warm question. Keep it brief and natural.</call_connected>"
            ),
        }
    ]


async def next_reply(
    history: list[dict],
    first_name: str = "",
    customer_phone: str = "",
) -> dict:
    """
    Run a tool-use loop until Claude produces a plain-text reply.
    Returns: {"reply": str, "action": str|None, "detail": str}
    """
    working = list(history)

    for _ in range(6):   # cap at 6 tool-call rounds to prevent runaway loops
        response = await _get_client().messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=500,
            system=_system_for(first_name),
            messages=working,
            tools=TOOL_DEFINITIONS,
            thinking={"type": "disabled"},
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            # No tool calls — this is the final spoken reply.
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            break

        # Execute every tool call and collect results.
        tool_results = []
        for tu in tool_uses:
            result_str = await execute_tool(tu.name, tu.input)
            print(f"[tool] {tu.name}({json.dumps(tu.input)[:120]}) → {result_str[:120]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
            })

        # Feed tool results back and continue the loop.
        working.append({"role": "assistant", "content": response.content})
        working.append({"role": "user", "content": tool_results})
    else:
        text = (
            "I wasn't able to check the calendar right now. "
            "I'll note your preference and someone from our team will call to confirm a time."
        )

    # Strip silent control commands from spoken text.
    action, detail = None, ""
    m = _CONTROL_RE.search(text)
    if m:
        action = m.group(1).upper()
        detail = (m.group(2) or "").strip()
        text = _CONTROL_RE.sub("", text).strip()

    # Safety-net: model emitted only a command with no spoken words.
    if not text:
        text = {
            "BOOK": "You're all set — that's booked. Thanks so much!",
            "INTERESTED": "Great — I'll make a note. Thanks for your time!",
            "CALLBACK": "No problem — we'll call you back at a better time. Thanks!",
            "NOT_INTERESTED": "No worries at all — thanks for your time, have a great day!",
            "DO_NOT_CALL": "Of course — I'll take you off our list right now. Sorry to bother you, take care.",
            "TRANSFER": "Let me connect you with someone from our team, one moment.",
            "END": "Thanks so much for your time. Have a great day!",
        }.get(action, "Thanks for chatting with us today!")

    return {"reply": text, "action": action, "detail": detail}
