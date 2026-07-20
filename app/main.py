from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.db.database import create_tables
from app.core.web import WEB_DIR
from app.api.campaigns import router as campaigns_router
from app.api.webhooks import router as webhooks_router
from app.api.audio import router as audio_router
from app.api.voice_agent import router as voice_agent_router, demo_router
from app.api.tools_webhook import router as tools_router
from app.api.business import router as business_router
from app.api.dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="Voxel AI",
    description="A configurable AI voice agent platform — one codebase, any business.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(campaigns_router)     # CSV upload, campaigns, launch, stats
app.include_router(webhooks_router)      # keypad (DTMF) call flow
app.include_router(audio_router)         # serves cached TTS audio to Twilio
app.include_router(voice_agent_router)   # conversational call flow (talks & listens)
app.include_router(demo_router)          # /demo browser chat + /demo/call
app.include_router(tools_router)         # /tools/vapi — Vapi server-tool webhook
app.include_router(business_router)      # /api/business-config — read/write business.json
app.include_router(dashboard_router)     # /api/dashboard — overview + call logs for the UI

# Static assets (css/js/images) for the marketing site + dashboard.
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.get("/")
async def home():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/dashboard")
async def dashboard():
    return FileResponse(WEB_DIR / "dashboard.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
