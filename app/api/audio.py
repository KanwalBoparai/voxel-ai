from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os

router = APIRouter(tags=["audio"])


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve cached ElevenLabs audio files to Twilio."""
    # Sanitize filename to prevent path traversal
    if "/" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")

    filepath = f"/tmp/{filename}"
    if not os.path.exists(filepath):
        raise HTTPException(404, "Audio file not found")

    return FileResponse(filepath, media_type="audio/mpeg")
