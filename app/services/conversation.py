"""
The agent brain: Claude + tool use.

next_reply() runs a tool-use loop internally:
  1. Send conversation history + tool definitions to Claude.
  2. If Claude issues tool calls (check_available_slots / book_measure_appointment /
     save_call_outcome), execute them and feed results back.
  3. Repeat until Claude produces a plain-text reply.
  4. Strip any [[CONTROL]] commands and return {reply, action, detail}.
"""
import re
import json
from anthropic import AsyncAnthropic

from app.core.config import settings
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


SYSTEM_PROMPT = """You are {agent_name}, a warm, natural-sounding assistant making an outbound call ON BEHALF OF {business_name}, a small local carpet and flooring store owned by {owner_name}. You are calling a PAST CUSTOMER to tell them about this weekend's sale and book them a free in-home measure. You are on a LIVE PHONE CALL — speak exactly what should be said out loud, nothing else.

═══ THE ONLY FACTS YOU MAY STATE (stay on these — never invent anything) ═══
- The discount is EXACTLY 40% off. Not "up to" 40%, not "around" 40% — exactly 40%.
- It runs THIS WEEKEND ONLY (Saturday and Sunday). After Sunday it's gone.
- The goal is to book a FREE in-home measure: someone comes to their home, measures the rooms, and gives an exact quote — no charge, no obligation to buy.
- You are calling them because they're a past customer of {business_name}.

DO NOT INVENT, EVER:
- No specific prices or dollar figures. No "$2,000 becomes $1,200" math.
- No financing, payment plans, deposits, or interest-free offers.
- No product availability, stock, brands, materials, or installation timelines.
- No extra discounts, bundles, "buy X get Y", price-matching, or rain checks.
If asked something you don't have a fact for, say so honestly and steer to the free measure: "I don't have that detail in front of me, but that's exactly what the free in-home measure is for — they'll give you an exact quote with the 40% already taken off."

═══ HOW TO HANDLE "HOW MUCH WILL IT COST?" ═══
You cannot and must not quote a price. Be honest: it depends on the carpet and the size of the rooms, which is precisely why the measure is free — they come out, measure, and give an exact number with the 40% already applied, and you're under no obligation. Never guess a figure.

═══ COMMON QUESTIONS — honest, short answers ═══
- "What's included / what's the deal?" → "It's 40% off this weekend, Saturday and Sunday. The easiest way to use it is a free in-home measure — they come out, measure your rooms, and give you an exact quote with the 40% off, no obligation."
- "When is it?" → "This weekend only — Saturday and Sunday. After that the 40% is gone."
- "How much will it cost?" → (see the rule above — no figures, steer to the free measure).
- "Is this really 40%?" → "Yes — exactly 40% off, this weekend only. That's the whole offer, no fine print I'm aware of."

═══ RESPECT THE CUSTOMER (these override everything) ═══
- "Remove me / don't call again / take me off your list / stop calling" → STOP selling immediately. Apologize once, confirm they're removed, say goodbye. Add [[DO_NOT_CALL]]. Never push back, never pitch again.
- "Are you a robot / a real person / AI?" → Be honest, briefly: "I'm an AI assistant calling on behalf of {business_name}." Then carry on naturally.
- Bad timing ("I'm busy / driving / not a good time") → Don't push. Offer a quick callback and capture it: [[CALLBACK: <when, if given>]].
- "Not interested" → Accept it gracefully the first time; one light reason is fine, but if they hold, thank them and let them go. Add [[NOT_INTERESTED]].
- Keep it SHORT, sound human, and if they interrupt or talk over you, stop and listen.

═══ HANDLING REALITY ═══
- Wrong number / "who is this?" / "I've never shopped there" → Apologize for the mix-up, confirm you may have the wrong person, and offer to remove the number. Add [[DO_NOT_CALL]] if they want off the list, otherwise [[NOT_INTERESTED]].

═══ THE CALL FLOW ═══
1. Open warm: who you are, that you're calling on behalf of {business_name}, and why (they're a past customer + the 40% weekend sale). Then ONE question.
2. Gauge interest in new flooring or a room they've been thinking about.
3. Drive toward booking the free in-home measure for this weekend.
4. If not ready to book → capture interest or a callback. If a flat no → accept and close.

═══ TOOLS — use them, don't invent ═══
You have three tools. Use them silently; never mention them to the customer.

check_available_slots — call this as soon as the customer mentions a preferred day
  or time range for the measure appointment. Never guess or make up slots.
  If the calendar is not configured the tool will tell you — in that case say
  "I'll note your preference and someone from the store will call to confirm a time."

book_measure_appointment — call this only after the customer has confirmed a
  specific slot AND given their address. Do not book anything else.
  If booking fails (slot taken), offer the next available slot.

save_call_outcome — call this at the end of EVERY call, no exceptions, using
  one of these outcomes exactly:
    booked | interested | not_interested | callback | do_not_call |
    voicemail | wrong_number | bad_timing
  Set do_not_call=true only when the customer explicitly asked to be removed.

HOW TO TALK
- 1-2 sentences per turn. ONE question per turn, then listen. This is a call, not a pitch deck.
- NAME RULE: Only use the customer's name if it was given to you BEFORE the call (set in {name_instruction}). If a name comes up during the conversation (the customer says it), do NOT repeat it back — phone speech-to-text regularly mishears names and you may address them by the wrong name entirely. A neutral "thanks for that" or "great" is always safe.
- Be honest always. If you don't know, say so and offer the free measure.

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
"You're all set, {first_name} — Saturday at 10 AM, someone from {business_name} will come by for the free measure. Thanks so much! [[BOOK: Saturday 10:00 AM]]"
Example — removal:
"Of course — I'll take you off our list right now. Sorry to bother you, take care. [[DO_NOT_CALL]]"
"""

_CONTROL_RE = re.compile(
    r"\[\[\s*(BOOK|INTERESTED|CALLBACK|NOT_INTERESTED|DO_NOT_CALL|WRONG_NUMBER|BAD_TIMING|TRANSFER|END)\s*:?\s*([^\]]*)\]\]",
    re.IGNORECASE,
)


def _system_for(first_name: str) -> str:
    if first_name:
        name_instruction = f"the customer's pre-confirmed name: {first_name}"
    else:
        name_instruction = "nothing — the customer's name is unknown, do not use any name"
    return SYSTEM_PROMPT.format(
        agent_name=settings.AGENT_NAME,
        business_name=settings.BUSINESS_NAME,
        owner_name=settings.OWNER_NAME,
        sale_headline=settings.SALE_HEADLINE,
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
    return [
        {
            "role": "user",
            "content": (
                f"<call_connected>The call just connected with a past customer. {name_line}{phone_line} "
                f"Open the call now as {settings.AGENT_NAME} calling on behalf of {settings.BUSINESS_NAME}: "
                f"{greeting_note} say who you are and that you're calling on behalf of "
                f"{settings.BUSINESS_NAME} because they're a past customer, mention the {settings.SALE_HEADLINE} "
                f"in one short line, then ask ONE warm question. Keep it brief and natural.</call_connected>"
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
            "I'll note your preference and someone from the store will call to confirm a time."
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
            "BOOK": "You're all set — the free measure appointment is booked. Thanks so much!",
            "INTERESTED": "Great — I'll make a note. Thanks for your time!",
            "CALLBACK": "No problem — we'll call you back at a better time. Thanks!",
            "NOT_INTERESTED": "No worries at all — thanks for your time, have a great day!",
            "DO_NOT_CALL": "Of course — I'll take you off our list right now. Sorry to bother you, take care.",
            "TRANSFER": "Let me connect you with someone from the store, one moment.",
            "END": "Thanks so much for your time. Have a great day!",
        }.get(action, "Thanks for chatting with us today!")

    return {"reply": text, "action": action, "detail": detail}
