from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager

from app.db.database import create_tables
from app.api.campaigns import router as campaigns_router
from app.api.webhooks import router as webhooks_router
from app.api.audio import router as audio_router
from app.api.voice_agent import router as voice_agent_router, demo_router
from app.api.tools_webhook import router as tools_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="Carpet Voice Agent",
    description="Conversational AI voice agent for carpet sales campaigns",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(campaigns_router)   # CSV upload, campaigns, launch, stats
app.include_router(webhooks_router)    # keypad (DTMF) call flow
app.include_router(audio_router)       # serves cached TTS audio to Twilio
app.include_router(voice_agent_router)  # conversational call flow (talks & listens)
app.include_router(demo_router)        # /demo browser chat + /demo/call
app.include_router(tools_router)       # /tools/vapi — Vapi server-tool webhook


@app.get("/")
async def home():
    return RedirectResponse(url="/demo")


@app.get("/health")
async def health():
    return {"status": "ok"}
