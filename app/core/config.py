from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Infrastructure & secrets only. Everything that describes the business
    itself (name, industry, services, hours, FAQs, tone, promotions) lives in
    config/business.json — see app/core/business_config.py — so swapping to a
    different business never requires touching this file or redeploying code.
    """

    # --- Database ---
    # Defaults to a local SQLite file so the app runs with ZERO database setup.
    # For Postgres, set DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/voxel_ai
    DATABASE_URL: str = "sqlite+aiosqlite:///./voxel_ai.db"

    # --- Claude (the agent brain) ---
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

    # --- Calling hours (24hr, used as a blanket outbound-dialing guard) ---
    CALL_START_HOUR: int = 9
    CALL_END_HOUR: int = 19

    # --- Google integrations (CRM + Calendar) ---
    # Provide one of: a path to the service-account JSON file, or the JSON as a string.
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""   # full JSON content as a single env var
    GOOGLE_CALENDAR_ID:   str = ""          # e.g. abc123@group.calendar.google.com
    GOOGLE_SHEET_ID:      str = ""          # spreadsheet ID from its URL

    # --- Vapi (cloud-hosted phone calls, no ngrok needed) ---
    VAPI_API_KEY: str = ""
    VAPI_PHONE_NUMBER_ID: str = ""

    # --- Business config file location (see app/core/business_config.py) ---
    BUSINESS_CONFIG_PATH: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
