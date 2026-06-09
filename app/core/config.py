from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Database ---
    # Defaults to a local SQLite file so the app runs with ZERO database setup.
    # For Postgres, set DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/carpet_agent
    DATABASE_URL: str = "sqlite+aiosqlite:///./carpet_agent.db"

    # --- Claude (the salesperson brain) ---
    ANTHROPIC_API_KEY: str = ""
    # Opus 4.8 is the most capable model. For snappier phone latency you can set
    # ANTHROPIC_MODEL=claude-haiku-4-5 (fastest) or claude-sonnet-4-6 (balanced).
    ANTHROPIC_MODEL: str = "claude-opus-4-8"

    # --- Twilio (places the real phone call + speech-to-text) ---
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # --- Text to speech ---
    # "elevenlabs" = lifelike voice (needs the keys below); "twilio" = built-in
    # neural voice (instant, no extra account). If ElevenLabs is selected but a
    # call fails, we automatically fall back to the Twilio voice.
    TTS_PROVIDER: str = "elevenlabs"
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = ""
    TWILIO_VOICE: str = "Polly.Joanna-Neural"  # used for the Twilio TTS fallback

    # --- App / publicly reachable base URL (ngrok or a domain) ---
    APP_BASE_URL: str = "http://localhost:8000"

    # --- Store / offer details (spoken by the agent) ---
    AGENT_NAME: str = "Sarah"
    BUSINESS_NAME: str = "Maple Carpet & Flooring"
    OWNER_NAME: str = "Priya"
    STORE_ADDRESS: str = ""
    STORE_PHONE: str = ""
    STORE_WEBSITE: str = ""
    # The ONLY facts the agent may state about the offer. Never invent pricing,
    # extra terms, or financing — the discount is exactly 40%, this weekend only.
    SALE_HEADLINE: str = "40% off, this weekend only"

    # --- Calling hours (24hr) ---
    CALL_START_HOUR: int = 10
    CALL_END_HOUR: int = 19

    # --- Google integrations (CRM + Calendar) ---
    # Provide one of: a path to the service-account JSON file, or the JSON as a string.
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""   # full JSON content as a single env var
    GOOGLE_CALENDAR_ID:   str = ""          # e.g. abc123@group.calendar.google.com
    GOOGLE_SHEET_ID:      str = ""          # spreadsheet ID from its URL
    APPOINTMENT_TIMEZONE: str = "America/Toronto"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
