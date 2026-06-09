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
    Generate audio for a script line, save to /tmp, and return a URL
    that Twilio can fetch. Returns the public URL.
    """
    import os
    import hashlib

    filename = f"{cache_key}_{hashlib.md5(text.encode()).hexdigest()[:8]}.mp3"
    filepath = f"/tmp/{filename}"

    if not os.path.exists(filepath):
        audio = await text_to_speech(text)
        with open(filepath, "wb") as f:
            f.write(audio)

    return f"{settings.APP_BASE_URL}/audio/{filename}"
