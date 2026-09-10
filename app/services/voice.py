import httpx
from app.core.config import settings


async def text_to_speech(text: str) -> bytes:
    """Convert text to speech using ElevenLabs and return raw MP3 bytes."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.80,
            "style": 0.20,
            "use_speaker_boost": True,
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.content


async def generate_and_cache(text: str, cache_key: str) -> str:
    """
    Generate audio for a script line, store it, and return the URL Twilio
    should fetch it from.

    The bytes go into the audio_clips table rather than /tmp: Twilio fetches
    the URL in a separate HTTP request, which on a serverless host lands in a
    different container with a different (empty) /tmp. Opening its own session
    keeps this callable from _say(), which has no request-scoped one.
    """
    import hashlib

    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.db.models import AudioClip

    filename = f"{cache_key}_{hashlib.md5(text.encode()).hexdigest()[:8]}.mp3"

    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(AudioClip.filename).where(AudioClip.filename == filename)
        )
        if existing.scalar_one_or_none() is None:
            audio = await text_to_speech(text)
            await db.merge(AudioClip(filename=filename, content=audio))
            await db.commit()

    return f"{settings.APP_BASE_URL}/audio/{filename}"
