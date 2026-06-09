from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from app.core.config import settings

# Lazily build the Twilio client so the app still boots (for /docs and the text
# simulator) when Twilio credentials aren't set yet.
_twilio_client = None


def get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN):
            raise RuntimeError(
                "Twilio credentials are not set. Add TWILIO_ACCOUNT_SID and "
                "TWILIO_AUTH_TOKEN to your .env to place real calls."
            )
        _twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _twilio_client


def make_call(to_phone: str, call_id: int, intro_path: str = "/webhook/call/intro") -> str:
    """
    Initiate an outbound call. Returns the Twilio CallSid.

    intro_path controls which flow runs:
      - "/webhook/call/intro"  -> the keypad (DTMF) script flow
      - "/voice/agent/start"   -> the conversational AI flow (talks & listens)
    """
    call = get_twilio_client().calls.create(
        to=to_phone,
        from_=settings.TWILIO_PHONE_NUMBER,
        url=f"{settings.APP_BASE_URL}{intro_path}?call_id={call_id}",
        status_callback=f"{settings.APP_BASE_URL}/voice/agent/status?call_id={call_id}",
        status_callback_method="POST",
        machine_detection="DetectMessageEnd",  # detects voicemail
        machine_detection_timeout=5,
    )
    return call.sid


# ---------- TwiML builders (keypad/DTMF flow — unchanged) ----------

def twiml_play_gather(audio_url: str, action: str, num_digits: int = 1, timeout: int = 8) -> str:
    """Build TwiML that plays audio and waits for a keypress."""
    response = VoiceResponse()
    gather = Gather(
        num_digits=num_digits,
        action=action,
        method="POST",
        timeout=timeout,
        action_on_empty_result=True,
    )
    gather.play(audio_url)
    response.append(gather)
    response.redirect(f"{action}&no_input=1")
    return str(response)


def twiml_play_and_end(audio_url: str) -> str:
    response = VoiceResponse()
    response.play(audio_url)
    response.hangup()
    return str(response)


def twiml_transfer(audio_url: str, transfer_to: str) -> str:
    response = VoiceResponse()
    response.play(audio_url)
    response.dial(transfer_to)
    return str(response)


def twiml_voicemail(audio_url: str) -> str:
    response = VoiceResponse()
    response.play(audio_url)
    response.hangup()
    return str(response)


def send_sms(to_phone: str, message: str):
    """Send an SMS after a call."""
    get_twilio_client().messages.create(
        to=to_phone,
        from_=settings.TWILIO_PHONE_NUMBER,
        body=message,
    )
