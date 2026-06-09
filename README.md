# Maple Carpet & Flooring — AI Voice Agent

An outbound AI voice agent built for Priya's carpet store weekend sale.

The agent calls past customers, tells them about the **40% off weekend sale**, drives toward booking a **free in-home measure appointment**, handles objections naturally, and saves every outcome to a CRM (Google Sheets) and calendar (Google Calendar) — all with strict guardrails to stay exactly on the facts given.

---

## What it does

```
Agent calls customer
       │
       ├─ Introduces itself as calling on behalf of Maple Carpet & Flooring
       ├─ Shares the 40% off weekend sale (exactly 40%, this weekend only)
       ├─ Drives toward a free in-home measure appointment
       │
       ├─ Customer asks "what's included?"    → honest answer, no invented details
       ├─ Customer asks "how much will it cost?" → no prices, steers to free measure
       ├─ Customer asks "are you AI?"          → yes, discloses honestly
       ├─ Customer says "I'm busy"             → offers callback, doesn't push
       ├─ Customer says "not interested"       → accepts gracefully, closes call
       ├─ Customer says "remove me"            → stops immediately, marks do-not-call
       │
       └─ Books slot via Google Calendar
          Saves outcome to Google Sheets CRM
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Agent brain | Claude Opus 4.8 (Anthropic SDK, async tool-use loop) |
| Phone calls | Vapi.ai — outbound dialing, STT, TTS (no ngrok needed) |
| Calendar | Google Calendar API — real availability check + booking |
| CRM | Google Sheets — one row per call, visible to store owner |
| Server | FastAPI + uvicorn |
| Local DB | SQLite (zero setup, stores transcripts + call records) |

---

## Project structure

```
app/
├── main.py                      # FastAPI app, router registration
├── core/config.py               # Pydantic settings (everything via .env)
├── api/
│   ├── voice_agent.py           # Twilio webhooks + /demo browser chat
│   └── tools_webhook.py         # POST /tools/vapi — Vapi server-tool webhook
├── services/
│   ├── conversation.py          # Claude tool-use loop, system prompt, control tags
│   ├── agent_tools.py           # Tool definitions (schemas) + shared executor
│   ├── google_calendar.py       # check_available_slots, book_measure_appointment
│   └── google_sheets.py         # save_call_outcome → CRM row
└── db/
    ├── models.py                 # SQLAlchemy models (Call, Customer, Appointment)
    └── database.py              # Async SQLite engine

vapi_call.py                     # Standalone script: place a real call via Vapi
tests/smoke_test.py              # Offline tests (no API keys needed)
RUNBOOK.md                       # Full setup + operational guide
```

---

## How the agent brain works

The conversation runs as a **tool-use loop** inside `next_reply()`:

```
1. Send conversation history + 3 tool definitions to Claude
2. Claude returns either:
     a) A tool_use block  →  execute the tool, feed result back, repeat
     b) Plain text        →  strip hidden [[CONTROL]] tag, return to caller
```

Three tools — all hitting real external services:

| Tool | What it does |
|------|-------------|
| `check_available_slots` | Reads Google Calendar, returns 2–3 free 1-hour slots for the weekend |
| `book_measure_appointment` | Checks for conflicts, creates a calendar event in the required format |
| `save_call_outcome` | Appends a row to Google Sheets with outcome, address, notes, do-not-call flag |

**Graceful degradation** — if Google credentials are not configured, the tools return helpful fallback messages and the agent adjusts ("I'll note your preference and the store will confirm directly") without crashing or making up information.

---

## Guardrails

The system prompt enforces a strict allow-list of facts:

**Agent may say:**
- Exactly 40% off, this weekend only
- The appointment is free, no obligation
- Final price depends on room size and product (a specialist confirms after the measure)

**Agent must never say:**
- Specific prices or estimates ("it'll cost around $X")
- Installation timelines or labour costs
- Financing, deposits, or payment terms
- Product brands or stock availability
- Any discount other than exactly 40%
- Any promotion not in the brief

**Name rule:** Only uses the customer's name if it was confirmed before the call. If the name comes from speech-to-text during the call, the agent does not echo it back — phone STT regularly mishears names.

---

## Captured outcomes

Every call ends with one outcome saved to the CRM:

| Outcome | When |
|---------|------|
| `booked` | Customer confirmed a specific appointment slot |
| `interested` | Positive but no slot locked in |
| `callback` | Bad timing — customer asked for a callback |
| `not_interested` | Customer declined |
| `do_not_call` | Customer asked to be removed — flagged permanently, never re-dialled |
| `voicemail` | Went to voicemail |
| `wrong_number` | Wrong person |
| `bad_timing` | Call disconnected without a clear outcome |

---

## Quick start

```bash
git clone https://github.com/yourusername/carpet-voice-agent.git
cd carpet-voice-agent
./setup.sh
```

Edit `.env` — minimum to run the text demo:
```
ANTHROPIC_API_KEY=sk-ant-...
```

Start the server:
```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open **http://localhost:8000/demo** — type as the customer, the same agent brain responds.

Run offline tests (no keys needed):
```bash
python tests/smoke_test.py
```

---

## Place a real call

Add to `.env`:
```
VAPI_API_KEY=...
VAPI_PHONE_NUMBER_ID=...
```

```bash
python vapi_call.py "+1 628 555 0100" "Jordan"
```

No ngrok. No server exposure. Vapi handles the call entirely in the cloud.

---

## Activate Google Calendar + CRM

See [RUNBOOK.md](RUNBOOK.md) for the full step-by-step setup.

Short version:
1. Create a Google Cloud service account, enable Calendar API + Sheets API
2. Share your calendar and spreadsheet with the service account email
3. Add to `.env`:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/key.json
   GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
   GOOGLE_SHEET_ID=your-spreadsheet-id
   ```

The "Call Outcomes" sheet is created automatically on the first saved call.

---

## Deploy to the cloud (Render)

The repo includes a [`render.yaml`](render.yaml) blueprint for one-click deployment.
Deploying gives you a public URL so Vapi can reach the tool webhook during a live call.

1. Go to [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint**.
2. Connect this GitHub repo — Render reads `render.yaml` and creates the web service.
3. In the dashboard, fill in the secret env vars (`ANTHROPIC_API_KEY`, and optionally
   `VAPI_*` and `GOOGLE_*`). The non-secret store details are pre-set in the blueprint.
4. After the first deploy, copy the service URL (e.g.
   `https://carpet-voice-agent.onrender.com`), set `APP_BASE_URL` to it, and point your
   Vapi tools at `{APP_BASE_URL}/tools/vapi`.

The live demo is then at `https://your-service.onrender.com/demo`.

> The free plan filesystem is ephemeral, so local SQLite resets on redeploy — that's
> fine, because the real CRM (Google Sheets) and calendar (Google Calendar) live
> externally. Boot is verified against Render's `$PORT` binding and `/health` check.

---

## What I'd build next

**Post-call SMS follow-up** — after a `booked` outcome, send a confirmation text to the customer with the appointment time. After `interested`, send a reminder that the sale ends Sunday. Both could run from the same `save_call_outcome` webhook without changing the agent logic.
