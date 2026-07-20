<div align="center">

# 🎙️ Voxel AI

### Your AI receptionist — for any business.

A configurable, production-ready **AI voice agent platform** that answers calls, books appointments, and captures leads in a natural voice. One codebase runs a dental clinic, a law firm, a restaurant, or an HVAC company — configured entirely through a JSON file, no code changes required.

[Live demo](#-running-locally) · [Dashboard](#-the-dashboard) · [Configuration](#-configuration) · [Deployment](#-deployment)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Opus%204.8-8B5CF6?logo=anthropic&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-4f46e5)

</div>

---

## 📖 Overview

**Voxel AI** is an AI-powered voice agent that acts as a front desk for small businesses. It places (and can answer) phone calls, holds a natural conversation powered by **Claude**, and takes real action — checking a live calendar, booking appointments, logging outcomes to a CRM, and sending SMS follow-ups.

What makes it a *platform* rather than a one-off bot: **every business-specific detail lives in configuration, not code.** Swap `config/business.json` (or edit it from the dashboard) and the same agent instantly becomes a specialist for a different industry — new name, persona, services, hours, FAQs, and booking flow, with zero redeploy.

```
   Caller ──▶ Twilio / Vapi ──▶ Claude (agent brain) ──▶ Tools
                                       │                   ├─ 📅 Google Calendar  (check + book)
                                       │                   ├─ 📊 Google Sheets    (CRM outcome)
                                       ▼                   └─ 💬 Twilio SMS        (follow-up)
                              config/business.json
                       (name · industry · services · hours · FAQs · tone)
```

---

## ✨ Features

- **🧠 Natural conversation** — Claude drives a real dialogue: handles objections, answers FAQs, discloses it's AI when asked, and never invents facts it wasn't given.
- **📅 Real appointment booking** — checks live Google Calendar availability with conflict detection and books straight in. No made-up slots.
- **📊 Automatic CRM logging** — every call ends with a structured outcome (`booked`, `interested`, `callback`, `do_not_call`, …) written to Google Sheets.
- **🔥 Lead scoring** — ranks every prospect 0–100 by engagement so the team follows up with the hottest leads first.
- **💬 SMS follow-ups** — automatically texts a recap, confirmation, or reminder after the call.
- **🛡️ Built-in guardrails** — stays strictly on configured facts, honors do-not-call instantly, and never pressures a caller.
- **⚙️ Config-driven** — industry, persona, services, hours, FAQs, promotions, and booking rules all come from JSON.
- **🖥️ Owner dashboard** — analytics, call logs with transcripts, appointments, and live-editable AI settings.
- **📞 Two call paths** — a full conversational flow (Claude) *and* a simpler keypad/DTMF flow, plus a **browser demo** that needs no phone.

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────────────────┐     ┌────────────────────┐
│  Web UI      │     │        FastAPI            │     │   External APIs    │
│  (web/)      │◀───▶│                          │◀───▶│                    │
│  landing     │     │  /demo   conversation    │     │  Anthropic (Claude)│
│  demo        │     │  /voice  Twilio webhooks │     │  Twilio / Vapi     │
│  dashboard   │     │  /tools  Vapi webhook    │     │  ElevenLabs (TTS)  │
└──────────────┘     │  /api    config + stats  │     │  Google Calendar   │
                     └────────────┬─────────────┘     │  Google Sheets     │
                                  │                    └────────────────────┘
                     ┌────────────┴─────────────┐
                     │  Business config (JSON)  │  ← the only file you edit
                     │  + SQLite / Postgres     │     to switch businesses
                     └──────────────────────────┘
```

**How the agent brain works** — `next_reply()` in `app/services/conversation.py` runs a tool-use loop:

1. Send conversation history + tool definitions to Claude, with a system prompt **generated from the business config**.
2. If Claude calls a tool (`check_available_slots` / `book_appointment` / `save_call_outcome`), execute it and feed the result back.
3. Repeat until Claude produces a plain-text reply.
4. Strip hidden `[[CONTROL]]` state tags and return `{reply, action, detail}` to the call-flow state machine.

If Google credentials aren't configured, the tools **degrade gracefully** — the agent says it'll note the preference for the team to confirm, instead of crashing or hallucinating.

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Agent brain** | Claude Opus 4.8 (Anthropic SDK, async tool-use loop) |
| **API server** | FastAPI + Uvicorn |
| **Phone calls** | Twilio (STT + TTS webhooks) or Vapi (cloud-hosted, no ngrok) |
| **Voice** | ElevenLabs (lifelike) with automatic Twilio-voice fallback |
| **Calendar** | Google Calendar API — live availability + booking |
| **CRM** | Google Sheets — one row per call |
| **Database** | SQLite by default (zero setup); Postgres-ready |
| **Frontend** | Vanilla HTML/CSS/JS — landing page, live demo, and dashboard (light/dark) |
| **Config** | Pydantic-validated JSON (`config/business.json`) |

---

## 🚀 Installation

```bash
git clone https://github.com/yourusername/voxel-ai.git
cd voxel-ai
./setup.sh          # creates .venv, installs deps, copies .env.example → .env
```

Or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## 🔑 Environment Variables

Infrastructure & secrets live in `.env`. **Business details do not** — they live in `config/business.json`.

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | ✅ | The agent brain (needed even for the browser demo) |
| `ANTHROPIC_MODEL` | – | Defaults to `claude-opus-4-8`; use `claude-haiku-4-5` for snappier latency |
| `BUSINESS_CONFIG_PATH` | – | Point at a different config, e.g. `config/examples/law_firm.json` |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_PHONE_NUMBER` | for calls | Places calls + speech-to-text |
| `VAPI_API_KEY` / `VAPI_PHONE_NUMBER_ID` | for cloud calls | Phone calls with no server exposure |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | – | Lifelike voice (falls back to Twilio voice) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` *or* `GOOGLE_SERVICE_ACCOUNT_JSON` | for CRM/calendar | Google service-account credentials |
| `GOOGLE_CALENDAR_ID` / `GOOGLE_SHEET_ID` | for CRM/calendar | Which calendar and sheet to use |
| `APP_BASE_URL` | for calls | Public URL Twilio/Vapi call back into |

See [`.env.example`](.env.example) for the full annotated list.

---

## 🖥️ Running Locally

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

| URL | What it is |
|-----|-----------|
| **http://localhost:8000** | Marketing landing page |
| **http://localhost:8000/demo** | 🎙️ Live voice demo — type as the caller, no phone needed |
| **http://localhost:8000/dashboard** | 📊 Business-owner dashboard |
| **http://localhost:8000/docs** | Interactive API docs (Swagger) |

Run the offline test suite (no API keys required):

```bash
python tests/smoke_test.py
```

---

## ⚙️ Configuration

The whole personality and knowledge of the agent is one JSON file. Change the business without touching a line of Python:

```jsonc
// config/business.json
{
  "business_name": "Bright Smile Dental Care",
  "industry": "dental clinic",
  "agent_name": "Ava",
  "tone": "warm, professional, and concise",
  "services": [
    { "name": "New patient exam & cleaning", "description": "Checkup, cleaning, and X-rays" }
  ],
  "faqs": [
    { "question": "Do you accept my insurance?", "answer": "We work with most major providers…" }
  ],
  "promotion": { "active": true, "headline": "Free new-patient exam this month" },
  "booking": { "appointment_label": "appointment", "requires_address": false },
  "hours": { "monday": { "open": "09:00", "close": "17:00", "closed": false } }
}
```

Ready-made industry starting points live in [`config/examples/`](config/examples/):

`dental` (default) · `law_firm` · `restaurant` · `real_estate` · `hvac` · `salon`

```bash
# Run as a law firm instead:
BUSINESS_CONFIG_PATH=config/examples/law_firm.json uvicorn app.main:app --reload
```

Business owners can also edit every field **from the dashboard** (AI Settings, Business Info, Knowledge Base) — changes apply to the live agent immediately.

---

## 📊 The Dashboard

A SaaS-style, light/dark dashboard for business owners:

- **Dashboard** — KPI cards, weekly call volume, outcome donut, recent calls
- **Analytics** — booking rate, hot leads, engagement, conversion funnel
- **Call Logs** — every call with a click-through transcript drawer
- **Appointments** — booking history
- **AI Settings / Business Info / Knowledge Base** — live-editable config (writes `business.json`)
- **Integrations** — live connection status for Claude, Twilio, Vapi, ElevenLabs, Google Calendar & Sheets

> Analytics and call logs read live data from the database and fall back to realistic sample data on a fresh install, so the dashboard is populated out of the box.

---

## 🧩 Example Use Cases

| Industry | The agent… |
|----------|-----------|
| 🦷 **Dental clinic** | Books new-patient exams, answers insurance questions |
| ⚖️ **Law firm** | Schedules free consultations, screens intake |
| 🏡 **Real estate** | Books valuations and buyer consultations |
| 🍽️ **Restaurant** | Takes reservations, answers menu/parking questions |
| 🔧 **HVAC / home services** | Books in-home quotes, triages emergency repairs |
| 💇 **Salon / spa** | Books appointments, handles first-time promos |
| 🩺 **Medical office** | Schedules visits, captures callbacks |
| 🚗 **Auto shop** | Books service, answers hours/pricing questions |

---

## 📁 Folder Structure

```
voxel-ai/
├── app/
│   ├── main.py                    # FastAPI app + routes + static mounting
│   ├── core/
│   │   ├── config.py              # Infra & secrets (Pydantic settings)
│   │   ├── business_config.py     # ⭐ Business config loader/saver (the platform core)
│   │   ├── calling_hours.py       # Outbound-dialing time guard
│   │   └── web.py                 # Path to the frontend
│   ├── api/
│   │   ├── voice_agent.py         # Conversational call flow + /demo endpoints
│   │   ├── webhooks.py            # Keypad (DTMF) call flow
│   │   ├── tools_webhook.py       # Vapi server-tool webhook
│   │   ├── business.py            # GET/PUT business config
│   │   ├── dashboard.py           # Dashboard aggregates + integration status
│   │   ├── campaigns.py           # CSV upload, campaigns, launch, stats
│   │   └── audio.py               # Serves cached TTS audio
│   ├── services/
│   │   ├── conversation.py        # ⭐ Claude tool-use loop + config-driven prompt
│   │   ├── agent_tools.py         # Tool schemas + shared executor
│   │   ├── google_calendar.py     # check_available_slots, book_appointment
│   │   ├── google_sheets.py       # save_call_outcome → CRM
│   │   ├── caller.py              # Twilio call + TwiML builders + SMS
│   │   ├── voice.py               # ElevenLabs TTS + caching
│   │   ├── followup.py            # Scheduled SMS follow-ups
│   │   ├── lead_scoring.py        # 0–100 engagement scoring
│   │   ├── reengagement.py        # Lapsed-customer detection
│   │   ├── abtest.py              # Script A/B variants
│   │   └── scheduler.py           # APScheduler background jobs
│   ├── scripts/templates.py       # Config-driven keypad-flow scripts
│   └── db/                        # SQLAlchemy models + async engine
├── config/
│   ├── business.json              # ⭐ The active business
│   └── examples/                  # dental, law, restaurant, real estate, hvac, salon
├── web/
│   ├── index.html                 # Landing page
│   ├── demo.html                  # Live voice demo
│   ├── dashboard.html             # Owner dashboard
│   └── assets/ (theme.css, app.js)
├── tests/smoke_test.py            # Offline tests (no keys needed)
├── vapi_call.py                   # Place a real call via Vapi
├── render.yaml                    # One-click Render deployment
└── RUNBOOK.md                     # Full operational setup guide
```

---

## ☁️ Deployment

A [`render.yaml`](render.yaml) blueprint deploys Voxel AI to [Render](https://render.com) in one click:

1. Push to GitHub → Render Dashboard → **New → Blueprint** → connect the repo.
2. Fill in the secret env vars (`ANTHROPIC_API_KEY`, and optionally `VAPI_*` / `GOOGLE_*`).
3. After the first deploy, set `APP_BASE_URL` to the service URL and point your Vapi tools at `{APP_BASE_URL}/tools/vapi`.

The live demo is then at `https://your-service.onrender.com/demo`. See [RUNBOOK.md](RUNBOOK.md) for full setup (Google Calendar + Sheets, real phone calls).

---

## 🗺️ Future Roadmap

- [ ] **Multi-tenant mode** — multiple businesses per deployment, DB-backed config
- [ ] **Inbound calls** — answer as well as place calls
- [ ] **Web voice widget** — real-time voice (not just text) in the browser demo
- [ ] **Analytics warehouse** — export call data to BigQuery / Postgres dashboards
- [ ] **More integrations** — HubSpot, Salesforce, Calendly, Outlook Calendar
- [ ] **Multilingual agents** — per-business language configuration
- [ ] **Auth + roles** — protected dashboard with owner/staff accounts

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repo and create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes and run the tests: `python tests/smoke_test.py`
3. Keep business logic **config-driven** — new business behavior should come from `business.json`, not hardcoded values.
4. Open a pull request describing the change.

Good first issues: add a new industry config to `config/examples/`, add a new integration card, or extend the analytics dashboard.

---

## 📄 License

Released under the [MIT License](LICENSE). Use it, fork it, ship it.

---

<div align="center">
<sub>Built with FastAPI · Claude · Twilio · Vapi · Google Workspace</sub>
</div>
