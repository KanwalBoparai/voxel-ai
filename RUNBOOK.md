# Voxel AI — Operations Runbook

A configurable AI voice agent that calls customers on behalf of **any business**,
holds a natural conversation (powered by Claude), books appointments, and logs
every outcome to a CRM (Google Sheets) and calendar (Google Calendar).

The business it represents is defined entirely in `config/business.json` — see
[Configuring a business](#configuring-a-business) below.

---

## Stack at a glance

| Layer | Technology | What it does |
|-------|-----------|-------------|
| Agent brain | **Claude** (Anthropic SDK) | Free-form conversation, tool-use loop |
| Phone calls | **Twilio** or **Vapi.ai** | Outbound dialing, STT, TTS |
| CRM | **Google Sheets** | Saves outcome of every call |
| Calendar | **Google Calendar** | Holds appointment slots |
| Database | **SQLite** | Local transcript + call record storage (zero setup) |
| Server | **FastAPI + Uvicorn** | Hosts the site, demo, and webhooks |
| Config | **`config/business.json`** | Everything business-specific |

---

## What you need

| # | Credential | Required for | Where to get it |
|---|-----------|-------------|-----------------|
| 1 | **Anthropic API key** | Agent brain (always) | platform.anthropic.com → API keys |
| 2 | **Vapi API key + phone number ID** | Real outbound calls | vapi.ai → Dashboard |
| 3 | **Google service account JSON** | Calendar + Sheets CRM | Google Cloud Console |
| 4 | **Google Calendar ID** | Appointment booking | Google Calendar → Settings → Integrate |
| 5 | **Google Sheet ID** | CRM outcome logging | URL of the spreadsheet |

> **Minimal setup** (browser demo only): only #1.
> **Real calls** (no phone lines needed): add #2.
> **Full CRM + calendar**: add #3–5.

---

## One-time setup

```bash
cd voxel-ai
./setup.sh                       # venv + deps + .env
# or manually:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your keys
```

Minimum `.env` to start the browser demo:

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-8
```

---

## Configuring a business

All business behavior lives in **`config/business.json`**. Edit it directly, or
edit it from the dashboard (AI Settings / Business Info / Knowledge Base pages).

Fields:

| Field | Meaning |
|-------|---------|
| `business_name`, `industry`, `tagline` | Identity |
| `agent_name`, `owner_name` | Who the agent is / represents |
| `phone`, `email`, `address`, `website`, `timezone` | Contact + scheduling timezone |
| `tone`, `greeting_style` | Agent personality |
| `services[]` | `{ name, description }` list the agent can speak to |
| `faqs[]` | `{ question, answer }` list — honest, no invention |
| `promotion` | `{ active, headline, details }` current offer |
| `booking` | `{ appointment_label, duration_minutes, requires_address, location_type }` |
| `hours` | Per-weekday `{ open, close, closed }` — drives calendar availability |

**Switch industries instantly** using one of the ready-made examples:

```bash
BUSINESS_CONFIG_PATH=config/examples/law_firm.json uvicorn app.main:app --reload
```

Available: `law_firm`, `restaurant`, `real_estate`, `hvac`, `salon` (and the default dental clinic in `config/business.json`).

---

## Rehearse in the browser (no phone, no extra accounts)

```bash
uvicorn app.main:app --reload
```

Open **http://localhost:8000/demo** and type as the caller. The exact same brain
that runs on real calls responds. Try these to test the guardrails:

| What you type | What the agent must do |
|--------------|----------------------|
| "How much does it cost?" | No invented prices — steer to booking |
| "Are you a real person?" | Disclose it's AI, then continue |
| "I'm busy right now." | Offer a callback, not push harder |
| "Remove me / don't call again." | Stop immediately, mark do-not-call |
| "Tuesday afternoon works." | Call `check_available_slots`, offer real slots |
| Pick a slot (+ address if required) | Call `book_appointment`, confirm booking |

When Google isn't configured the calendar tools degrade gracefully — the agent
notes the preference and says the team will confirm directly.

---

## Place a real outbound call (Vapi)

Add to `.env`:

```
VAPI_API_KEY=your-vapi-private-key
VAPI_PHONE_NUMBER_ID=your-vapi-phone-number-id
```

Then:

```bash
python vapi_call.py "+1 628 555 0100" "Jordan"
```

The assistant is generated from `config/business.json`, so it speaks as whatever
business is currently configured.

> **No ngrok needed.** Vapi handles the call entirely in the cloud.
> **Free Vapi numbers are US-only.**

---

## Activate Google Calendar + CRM

### Step 1 — Google Cloud setup
1. [console.cloud.google.com](https://console.cloud.google.com) → create a project.
2. Enable **Google Calendar API** and **Google Sheets API**.
3. **IAM → Service Accounts** → create one → create + download a JSON key.

### Step 2 — Share your Calendar
1. Google Calendar → Settings → your calendar → **Share with specific people**.
2. Add the service account email → permission **Make changes to events**.
3. Copy the **Calendar ID** (e.g. `abc123@group.calendar.google.com`).

### Step 3 — Share your Sheet
1. Create a Google Sheet (or reuse one) → share with the service account email → **Editor**.
2. Copy the **Sheet ID** from the URL: `.../spreadsheets/d/`**`THIS-PART`**`/edit`.

### Step 4 — Add to `.env`
```
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
GOOGLE_CALENDAR_ID=abc123@group.calendar.google.com
GOOGLE_SHEET_ID=your-spreadsheet-id
```

The **"Call Outcomes"** sheet tab is created automatically on the first saved call.
The appointment timezone comes from `config/business.json` (`timezone`).

---

## Vapi tool webhooks (for real calls with booking)

For real phone calls, Vapi reaches your server to run the tools. Set
`APP_BASE_URL` to your public URL (deploy, or ngrok for local testing):

```
APP_BASE_URL=https://your-server.example.com
```

In **Vapi → Assistant → Tools**, add three tools of type **Function (Server)**:

| Tool name | Server URL |
|-----------|-----------|
| `check_available_slots` | `{APP_BASE_URL}/tools/vapi` |
| `book_appointment` | `{APP_BASE_URL}/tools/vapi` |
| `save_call_outcome` | `{APP_BASE_URL}/tools/vapi` |

All three share the same endpoint — the server routes by tool name.

---

## Monitoring outcomes

- **Dashboard**: `http://localhost:8000/dashboard` → Call Logs & Analytics.
- **Google Sheets** (if configured): the shared spreadsheet → "Call Outcomes" tab.
- **Local transcript**: `curl http://localhost:8000/demo/call/1/transcript`
- **Server console**: every agent turn and tool call is printed live.

---

## How it works end-to-end

```
Customer phone
     │  (Twilio or Vapi dials)
     ▼
  STT ──► text ──► Claude (tool-use loop)
                         │
                 tool call needed?
                  │             │
                YES             NO
                  │             │
        POST /tools/vapi     spoken reply
          (FastAPI)         ◄── TTS ──
               │
      execute_tool() dispatcher
     ┌─────────┼─────────┐
     ▼         ▼         ▼
  Calendar  Calendar   Sheets
  check     book       save outcome
```

The **browser demo** uses Claude directly via the Anthropic tool-use API — the
same three tools run inside `next_reply()` in `app/services/conversation.py`.

---

## Captured outcomes

| Outcome | When |
|---------|------|
| `booked` | Customer confirmed an appointment slot |
| `interested` | Positive but no slot booked |
| `callback` | Bad timing — asked to be called back |
| `not_interested` | Customer declined |
| `do_not_call` | Asked to be removed — flagged permanently |
| `voicemail` | Went to voicemail |
| `wrong_number` | Wrong person |
| `bad_timing` | Disengaged mid-call |

---

## Tuning

| File | What to change |
|------|---------------|
| `config/business.json` | **Everything business-specific** — name, services, hours, FAQs, tone, promotion, booking |
| `.env` | Secrets + infrastructure (API keys, base URL, calling hours) |
| `app/services/conversation.py` | The prompt *template* (call flow, guardrails) — rarely needed |
| `app/services/google_calendar.py` | Slot duration (`SLOT_DURATION`), slot logic |
