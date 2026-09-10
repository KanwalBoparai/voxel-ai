from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import AudioClip

router = APIRouter(tags=["audio"])


@router.get("/audio/{filename}")
async def serve_audio(filename: str, db: AsyncSession = Depends(get_db)):
    """
    Serve cached ElevenLabs audio to Twilio.

    Reads from the audio_clips table rather than /tmp — Twilio fetches this URL
    in a separate request, which on a serverless host is a different container
    than the one that generated the speech. See app/services/voice.py.
    """
    result = await db.execute(
        select(AudioClip.content).where(AudioClip.filename == filename)
    )
    content = result.scalar_one_or_none()
    if content is None:
        raise HTTPException(404, "Audio file not found")

    # Twilio re-fetches the same clip across retries, so let it be cached.
    return Response(
        content=content,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
