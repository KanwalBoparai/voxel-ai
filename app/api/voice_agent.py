"""
Conversational voice agent.

Twilio calls the customer, transcribes their speech (<Gather input="speech">),
and on each turn we ask Claude what the salesperson should say next, speak it
(ElevenLabs, or Twilio's built-in voice), and listen again — until the agent
books a visit, transfers to a human, or the call ends.

Also exposes a few demo helpers:
  POST /demo/call            -> place a live conversational call to a number
  GET  /demo                 -> a tiny browser chat to rehearse the agent (no phone)
  POST /demo/chat            -> one text turn against the same brain
  GET  /demo/call/{id}/transcript -> the full conversation of a call
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from twilio.twiml.voice_response import VoiceResponse, Gather
from datetime import datetime, timezone
from pydantic import BaseModel
import phonenumbers

from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Call, Customer, Campaign, CallStatus, CallOutcome, Appointment
from app.services.voice import generate_and_cache
from app.services.caller import make_call
from app.services import conversation
from app.core.config import settings
from app.core.business_config import business_config
from app.core.web import WEB_DIR

router = APIRouter(prefix="/voice/agent", tags=["voice-agent"])
demo_router = APIRouter(prefix="/demo", tags=["demo"])


# ----------------------------- speech helpers -----------------------------

async def _say(node, text: str, cache_key: str):
    """Append spoken text to a VoiceResponse or Gather, via ElevenLabs or Twilio."""
    use_eleven = (
        settings.TTS_PROVIDER == "elevenlabs"
        and settings.ELEVENLABS_API_KEY
        and settings.ELEVENLABS_VOICE_ID
    )
    if use_eleven:
        try:
            url = await generate_and_cache(text, cache_key)
            node.play(url)
            return
        except Exception as e:  # fall back so a TTS hiccup never kills the call
            print(f"[tts] ElevenLabs failed ({e}); using Twilio voice")
    node.say(text, voice=settings.TWILIO_VOICE)


def _first_name(customer: Customer | None) -> str:
    if customer and customer.name:
        return customer.name.split()[0]
    return ""


async def _gather_response(text: str, call_id: int, turn: int, attempts: int = 0) -> str:
    """Speak `text`, then listen for the customer's reply."""
    vr = VoiceResponse()
    gather = Gather(
        input="speech",
        speech_timeout="auto",
        action=f"{settings.APP_BASE_URL}/voice/agent/turn?call_id={call_id}&attempts={attempts}",
        method="POST",
        action_on_empty_result=True,
    )
    await _say(gather, text, f"c{call_id}_t{turn}")
    vr.append(gather)
    return str(vr)


async def _say_and_hangup(text: str, call_id: int, turn: int) -> str:
    vr = VoiceResponse()
    await _say(vr, text, f"c{call_id}_t{turn}")
    vr.hangup()
    return str(vr)


def _xml(twiml: str) -> PlainTextResponse:
    return PlainTextResponse(twiml, media_type="application/xml")


async def _load_call(call_id: int, db: AsyncSession):
    result = await db.execute(
        select(Call, Customer).join(Customer, Call.customer_id == Customer.id).where(Call.id == call_id)
    )
    row = result.first()
    return (row[0], row[1]) if row else (None, None)


def _print_turn(call_id: int, speaker: str, text: str):
    print(f"\n📞 [call {call_id}] {speaker}: {text}", flush=True)


# ----------------------------- Twilio webhooks -----------------------------

@router.post("/start")
async def agent_start(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Call connected — the agent greets the customer and starts the conversation."""
    form = await request.form()
    answered_by = form.get("AnsweredBy", "human")

    call, customer = await _load_call(call_id, db)
    if not call:
        return _xml("<Response><Hangup/></Response>")

    first = _first_name(customer)

    # Voicemail detected -> leave a short message and hang up.
    if answered_by in ("machine_start", "machine_end_beep", "machine_end_silence"):
        promo = business_config.promotion
        promo_line = f" We're currently offering {promo.headline.lower()}, and we'd" if (promo.active and promo.headline) else " We'd"
        vm = (
            f"Hi {first or 'there'}, this is {business_config.agent_name} calling on behalf of "
            f"{business_config.business_name}.{promo_line} love to get you booked in. "
            f"Give us a call back if you're interested. Thanks!"
        )
        call.status = CallStatus.voicemail
        call.outcome = CallOutcome.voicemail_left
        call.started_at = datetime.now(timezone.utc)
        await db.commit()
        _print_turn(call_id, "voicemail", vm)
        return _xml(await _say_and_hangup(vm, call_id, 0))

    # Human answered — generate the opening line from Claude.
    history = conversation.initial_history(first, customer_phone=customer.phone if customer else "")
    result = await conversation.next_reply(history, first, customer_phone=customer.phone if customer else "")
    history.append({"role": "assistant", "content": result["reply"]})

    call.status = CallStatus.in_progress
    call.started_at = datetime.now(timezone.utc)
    call.transcript = history
    await db.commit()

    _print_turn(call_id, business_config.agent_name, result["reply"])
    return _xml(await _gather_response(result["reply"], call_id, turn=len(history)))


@router.post("/turn")
async def agent_turn(request: Request, call_id: int, attempts: int = 0, db: AsyncSession = Depends(get_db)):
    """Customer spoke — figure out the agent's next line and speak it."""
    form = await request.form()
    speech = (form.get("SpeechResult") or "").strip()

    call, customer = await _load_call(call_id, db)
    if not call:
        return _xml("<Response><Hangup/></Response>")

    history = list(call.transcript or [])
    # Inbound callers have no pre-confirmed name, so don't feed the placeholder
    # ("Inbound caller") to the agent as if it were their real name.
    first = "" if conversation.is_inbound(history) else _first_name(customer)

    # No speech captured — re-prompt once or twice, then wrap up.
    if not speech:
        if attempts >= 2:
            bye = "I'll let you go for now. Thanks so much, and have a wonderful day!"
            call.status = CallStatus.completed
            await db.commit()
            _print_turn(call_id, business_config.agent_name, bye)
            return _xml(await _say_and_hangup(bye, call_id, turn=len(history) + 1))
        nudge = "Sorry, I didn't quite catch that — are you still there?"
        _print_turn(call_id, business_config.agent_name, f"(no speech) {nudge}")
        return _xml(await _gather_response(nudge, call_id, turn=len(history) + 1, attempts=attempts + 1))

    _print_turn(call_id, customer.name or "Customer", speech)
    history.append({"role": "user", "content": speech})

    result = await conversation.next_reply(history, first, customer_phone=customer.phone if customer else "")
    reply, action, detail = result["reply"], result["action"], result["detail"]
    history.append({"role": "assistant", "content": reply})
    call.transcript = history
    _print_turn(call_id, business_config.agent_name, reply + (f"  ⟶ [{action} {detail}]" if action else ""))

    if action == "BOOK":
        label = business_config.booking.appointment_label.capitalize()
        db.add(Appointment(
            customer_id=call.customer_id,
            call_id=call.id,
            scheduled_at=datetime.now(timezone.utc),
            notes=f"{label} requested: {detail}" if detail else f"{label} booked during call",
        ))
        call.outcome = CallOutcome.appointment_booked
        call.status = CallStatus.completed
        await db.commit()
        return _xml(await _say_and_hangup(reply, call_id, turn=len(history)))

    if action == "DO_NOT_CALL":
        # Honor the request immediately and permanently.
        customer.do_not_call = True
        call.outcome = CallOutcome.not_interested
        call.status = CallStatus.do_not_call
        call.notes = "Customer asked to be removed (do-not-call)."
        await db.commit()
        return _xml(await _say_and_hangup(reply, call_id, turn=len(history)))

    if action in ("INTERESTED", "CALLBACK", "NOT_INTERESTED", "WRONG_NUMBER", "BAD_TIMING"):
        call.outcome = {
            "INTERESTED":    CallOutcome.interested,
            "CALLBACK":      CallOutcome.callback_requested,
            "NOT_INTERESTED": CallOutcome.not_interested,
            "WRONG_NUMBER":  CallOutcome.wrong_number,
            "BAD_TIMING":    CallOutcome.bad_timing,
        }[action]
        call.status = CallStatus.completed
        if detail:
            call.notes = f"{action.lower()}: {detail}"
        await db.commit()
        return _xml(await _say_and_hangup(reply, call_id, turn=len(history)))

    if action == "TRANSFER":
        call.outcome = CallOutcome.transferred
        call.status = CallStatus.completed
        await db.commit()
        vr = VoiceResponse()
        await _say(vr, reply, f"c{call_id}_t{len(history)}")
        if business_config.phone:
            vr.dial(business_config.phone)
        else:
            vr.hangup()
        return _xml(str(vr))

    if action == "END":
        call.status = CallStatus.completed
        await db.commit()
        return _xml(await _say_and_hangup(reply, call_id, turn=len(history)))

    # Normal turn — keep the conversation going.
    await db.commit()
    return _xml(await _gather_response(reply, call_id, turn=len(history)))


@router.post("/status")
async def agent_status(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Twilio status callback — record final status and duration."""
    form = await request.form()
    twilio_status = form.get("CallStatus", "")
    duration = form.get("CallDuration", 0)

    call, _ = await _load_call(call_id, db)
    if not call:
        return PlainTextResponse("OK")

    status_map = {
        "no-answer": CallStatus.no_answer,
        "busy": CallStatus.no_answer,
        "failed": CallStatus.failed,
        "canceled": CallStatus.failed,
    }
    if twilio_status in status_map:
        call.status = status_map[twilio_status]
    elif call.status == CallStatus.in_progress:
        call.status = CallStatus.completed

    try:
        call.duration_seconds = int(duration)
    except (TypeError, ValueError):
        pass
    call.ended_at = datetime.now(timezone.utc)
    await db.commit()
    return PlainTextResponse("OK")


# ----------------------------- inbound calls -----------------------------

async def _get_inbound_campaign(db: AsyncSession) -> Campaign:
    result = await db.execute(select(Campaign).where(Campaign.name == "Inbound"))
    campaign = result.scalar_one_or_none()
    if not campaign:
        campaign = Campaign(name="Inbound", script_key="conversation")
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
    return campaign


@router.post("/inbound")
async def agent_inbound(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Twilio hits this when someone CALLS the business number (point the number's
    Voice webhook at {APP_BASE_URL}/voice/agent/inbound). The agent answers,
    then the conversation runs through the same /turn loop as outbound calls.
    """
    form = await request.form()
    from_number = (form.get("From") or "").strip() or f"anon-{int(datetime.now(timezone.utc).timestamp())}"

    # Upsert the caller as a customer so the call is logged like any other.
    result = await db.execute(select(Customer).where(Customer.phone == from_number))
    customer = result.scalar_one_or_none()
    if not customer:
        customer = Customer(name="Inbound caller", phone=from_number)
        db.add(customer)
        await db.commit()
        await db.refresh(customer)

    campaign = await _get_inbound_campaign(db)
    call = Call(
        customer_id=customer.id,
        campaign_id=campaign.id,
        status=CallStatus.in_progress,
        scheduled_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        transcript=[],
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # Greet the caller (inbound framing is carried by the seed marker so every
    # later /turn keeps answering as "we picked up", not "we're calling you").
    history = conversation.inbound_history(customer_phone=customer.phone)
    reply = await conversation.next_reply(history, first_name="", customer_phone=customer.phone)
    history.append({"role": "assistant", "content": reply["reply"]})
    call.transcript = history
    await db.commit()

    _print_turn(call.id, business_config.agent_name, reply["reply"])
    return _xml(await _gather_response(reply["reply"], call.id, turn=len(history)))


# ----------------------------- demo helpers -----------------------------

class DemoCall(BaseModel):
    phone: str
    name: str = "there"


def _to_e164(raw: str) -> str:
    try:
        parsed = phonenumbers.parse(raw, "US")
    except phonenumbers.NumberParseException:
        raise HTTPException(400, f"'{raw}' is not a valid phone number")
    if not phonenumbers.is_valid_number(parsed):
        raise HTTPException(400, f"'{raw}' is not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


async def _get_demo_campaign(db: AsyncSession) -> Campaign:
    result = await db.execute(select(Campaign).where(Campaign.name == "Voice Demo"))
    campaign = result.scalar_one_or_none()
    if not campaign:
        campaign = Campaign(name="Voice Demo", script_key="conversation")
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
    return campaign


@demo_router.post("/call")
async def demo_call(data: DemoCall, db: AsyncSession = Depends(get_db)):
    """Place a live conversational call to a phone number. Returns the call id."""
    e164 = _to_e164(data.phone)
    campaign = await _get_demo_campaign(db)

    result = await db.execute(select(Customer).where(Customer.phone == e164))
    customer = result.scalar_one_or_none()
    if customer:
        # Honor the do-not-call list — never re-dial someone who opted out.
        if customer.do_not_call:
            raise HTTPException(403, f"{e164} is on the do-not-call list and will not be dialed.")
        customer.name = data.name
    else:
        customer = Customer(name=data.name, phone=e164)
        db.add(customer)
    await db.commit()
    await db.refresh(customer)

    call = Call(
        customer_id=customer.id,
        campaign_id=campaign.id,
        status=CallStatus.pending,
        scheduled_at=datetime.now(timezone.utc),
        transcript=[],
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    try:
        sid = make_call(e164, call.id, intro_path="/voice/agent/start")
        call.twilio_call_sid = sid
        call.status = CallStatus.in_progress
        await db.commit()
    except Exception as e:
        call.status = CallStatus.failed
        call.notes = str(e)
        await db.commit()
        raise HTTPException(500, f"Could not place call: {e}")

    return {
        "call_id": call.id,
        "calling": e164,
        "transcript_url": f"{settings.APP_BASE_URL}/demo/call/{call.id}/transcript",
        "message": f"Calling {data.name} now — watch your server console for the live conversation.",
    }


@demo_router.get("/call/{call_id}/transcript")
async def call_transcript(call_id: int, db: AsyncSession = Depends(get_db)):
    """The full conversation for a call (agent + customer turns)."""
    call, customer = await _load_call(call_id, db)
    if not call:
        raise HTTPException(404, "Call not found")
    turns = []
    for t in (call.transcript or []):
        content = t.get("content", "")
        if isinstance(content, str) and content.startswith("<call_connected>"):
            continue  # hide the internal kickoff prompt
        turns.append({
            "speaker": business_config.agent_name if t.get("role") == "assistant" else (customer.name or "Customer"),
            "text": content,
        })
    return {
        "call_id": call.id,
        "customer": customer.name if customer else None,
        "status": call.status.value if call.status else None,
        "outcome": call.outcome.value if call.outcome else None,
        "turns": turns,
    }


# --- text simulator: rehearse the agent in a browser, no phone needed ---

_sim_sessions: dict[str, dict] = {}


class ChatTurn(BaseModel):
    session_id: str = "default"
    message: str = ""
    name: str = "there"


@demo_router.post("/chat")
async def demo_chat(turn: ChatTurn):
    """One text turn against the live agent brain. Empty message starts the call."""
    sess = _sim_sessions.get(turn.session_id)
    if sess is None or not turn.message:
        history = conversation.initial_history(turn.name)
        result = await conversation.next_reply(history, turn.name)
        history.append({"role": "assistant", "content": result["reply"]})
        _sim_sessions[turn.session_id] = {"history": history, "name": turn.name}
        return {"reply": result["reply"], "action": result["action"], "detail": result["detail"]}

    history = sess["history"]
    history.append({"role": "user", "content": turn.message})
    result = await conversation.next_reply(history, sess["name"])
    history.append({"role": "assistant", "content": result["reply"]})
    if result["action"] in (
        "BOOK", "INTERESTED", "CALLBACK", "NOT_INTERESTED",
        "DO_NOT_CALL", "WRONG_NUMBER", "BAD_TIMING", "TRANSFER", "END"
    ):
        _sim_sessions.pop(turn.session_id, None)  # conversation finished
    return {"reply": result["reply"], "action": result["action"], "detail": result["detail"]}


@demo_router.get("")
async def demo_page():
    """Serve the live voice-demo page (branding is fetched client-side from /api/business-config)."""
    return FileResponse(WEB_DIR / "demo.html")

