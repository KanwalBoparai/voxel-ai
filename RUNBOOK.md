# Maple Carpet & Flooring — Voice Agent Runbook

A conversational AI that calls past customers on behalf of **Maple Carpet & Flooring**,
pitches the **40% off weekend sale**, drives toward a **free in-home measure appointment**,
and saves every outcome to a CRM (Google Sheets) and calendar (Google Calendar).

---

## Stack at a glance

| Layer | Technology | What it does |
|-------|-----------|-------------|
| Agent brain | **Claude** (Anthropic SDK) | Free-form conversation, tool-use loop |
| Phone calls | **Vapi.ai** | Outbound dialing, STT, TTS — no ngrok needed |
| CRM | **Google Sheets** | Saves outcome of every call; visible to store owner |
| Calendar | **Google Calendar** | Holds measure appointment slots; shared with store |
| Database | **SQLite** | Local transcript + call record storage (zero setup) |
| Server | **FastAPI + uvicorn** | Hosts the demo chat and Vapi tool webhooks |

---

## What you need

| # | Credential | Required for | Where to get it |
|---|-----------|-------------|-----------------|
| 1 | **Anthropic API key** | Agent brain (always needed) | platform.anthropic.com → API keys |
| 2 | **Vapi API key + phone number ID** | Real outbound calls | vapi.ai → Dashboard |
| 3 | **Google service account JSON** | Calendar + Sheets CRM | Google Cloud Console |
| 4 | **Google Calendar ID** | Appointment booking | Google Calendar → Settings → Integrate |
| 5 | **Google Sheet ID** | CRM outcome logging | URL of the spreadsheet |

> **Minimal setup** (text demo only): you only need #1.  
> **Real calls** (no phone lines needed): add #2.  
> **Full CRM + calendar**: add #3–5.

---

## One-time setup

```bash
cd carpet-voice-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then fill in your keys
```

Minimum `.env` to start the text demo:

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-8
AGENT_NAME=Sarah
BUSINESS_NAME=Maple Carpet & Flooring
OWNER_NAME=Priya
SALE_HEADLINE=40% off, this weekend only
```

---

## Rehearse in the browser (no phone, no extra accounts)

```bash
uvicorn app.main:app --reload
```

Open **http://localhost:8000/demo**

Type as the customer. The exact same brain that runs on real calls responds.
Try these to test the guardrails:

| What you type | What the agent must do |
|--------------|----------------------|
| "How much will it cost?" | No prices — steer to free measure |
| "Is this really 40%?" | Confirm exactly 40%, this weekend only |
| "Are you a real person?" | Disclose it's AI, then continue |
| "I'm busy right now." | Offer a callback, not push harder |
| "Remove me / don't call again." | Stop immediately, mark do-not-call |
| "Saturday afternoon works." | Call `check_available_slots`, offer real slots |
| Pick a slot + give an address | Call `book_measure_appointment`, confirm booking |

When Google is not configured the calendar tools degrade gracefully:
the agent notes the preference and tells the customer the store will confirm directly.

---

## Place a real outbound call (Vapi)

Add to `.env`:

```
VAPI_API_KEY=your-vapi-private-key
VAPI_PHONE_NUMBER_ID=your-vapi-phone-number-id
```

Trigger a call from the terminal:

```bash
curl -X POST https://api.vapi.ai/call/phone \
  -H "Authorization: Bearer $VAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "phoneNumberId": "'$VAPI_PHONE_NUMBER_ID'",
    "customer": { "number": "+1XXXXXXXXXX" },
    "assistant": {
      "firstMessage": "Hi there — this is Sarah calling on behalf of Maple Carpet and Flooring. Is now a quick moment?",
      "model": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "systemPrompt": "You are Sarah, an AI assistant calling on behalf of Maple Carpet and Flooring. The store is running 40% off this weekend only. Offer a free in-home measure appointment."
      },
      "voice": { "provider": "openai", "voiceId": "nova" },
      "startSpeakingPlan": { "waitSeconds": 2 }
    }
  }'
```

> **No ngrok needed.** Vapi handles the call entirely in the cloud.  
> **Free Vapi numbers are US-only.** Canadian numbers (+1-416, +1-437, etc.) will not receive incoming calls from a free Vapi number. US numbers work fine.

---

## Activate Google Calendar + CRM

### Step 1 — Google Cloud setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project.
2. Enable **Google Calendar API** and **Google Sheets API**.
3. Go to **IAM → Service Accounts** → Create a service account.
4. Create a JSON key for it and download it.

### Step 2 — Share your Calendar

1. Open Google Calendar → Settings → your calendar → **Share with specific people**.
2. Add the service account email (looks like `name@project.iam.gserviceaccount.com`).
3. Permission: **Make changes to events**.
4. Copy the **Calendar ID** (looks like `abc123@group.calendar.google.com`).

### Step 3 — Share your Sheet

1. Create a new Google Sheet (or use an existing one).
2. Share it with the service account email — **Editor** permission.
3. Copy the **Sheet ID** from the URL:  
   `https://docs.google.com/spreadsheets/d/`**`THIS-PART`**`/edit`

### Step 4 — Add to `.env`

```
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
GOOGLE_CALENDAR_ID=abc123@group.calendar.google.com
GOOGLE_SHEET_ID=your-spreadsheet-id
APPOINTMENT_TIMEZONE=America/Toronto
```

The sheet tab **"Call Outcomes"** is created automatically on the first saved call.

---

## Vapi tool webhooks (for real calls with booking)

For real phone calls, Vapi needs to reach your server to call the three tools.
Set `APP_BASE_URL` in `.env` to your public server URL (deploy it, or use ngrok for local testing):

```
APP_BASE_URL=https://your-server.example.com
```

Then in **Vapi → Assistant → Tools**, add three tools of type **Function (Server)**:

| Tool name | Server URL |
|-----------|-----------|
| `check_available_slots` | `{APP_BASE_URL}/tools/vapi` |
| `book_measure_appointment` | `{APP_BASE_URL}/tools/vapi` |
| `save_call_outcome` | `{APP_BASE_URL}/tools/vapi` |

All three share the same webhook endpoint — the server routes by tool name.

---

## View call outcomes

**Google Sheets** (if configured): open the shared spreadsheet — "Call Outcomes" tab.  
One row per call: timestamp, name, phone, outcome, appointment date/time, address, notes, do-not-call flag.

**Local transcript** (always available):

```bash
curl http://localhost:8000/demo/call/1/transcript
```

**Server console**: every agent turn and tool call is printed live as the call happens.

---

## How it works end-to-end

```
Customer phone
     │
     │  (Vapi dials)
     ▼
  Vapi.ai  ──STT──►  text  ──►  LLM (GPT-4o-mini in Vapi)
                                      │
                              tool call needed?
                               │             │
                             YES             NO
                               │             │
                    POST /tools/vapi      spoken reply
                       (FastAPI)         ◄── TTS ── Vapi
                            │
               execute_tool() dispatcher
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    Google Calendar    Google Calendar   Google Sheets
    check slots        book appointment  save outcome
```

**Text demo** uses Claude directly with the Anthropic tool-use API — the same
three tools run inside the `next_reply()` loop in `app/services/conversation.py`.

---

## Captured outcomes

Every call ends with exactly one of these written to the CRM:

| Outcome | When |
|---------|------|
| `booked` | Customer confirmed a measure appointment slot |
| `interested` | Positive but no slot booked (calendar unavailable / customer undecided) |
| `callback` | Bad timing — customer asked to be called back |
| `not_interested` | Customer declined |
| `do_not_call` | Customer asked to be removed — flagged permanently |
| `voicemail` | Call went to voicemail, short message left |
| `wrong_number` | Number doesn't belong to a Maple Carpet customer |
| `bad_timing` | Customer disengaged mid-call without a clear outcome |

---

## What the agent is allowed to say

- The call is on behalf of **Maple Carpet & Flooring**.
- The sale is **exactly 40% off**, **this weekend only**.
- There is a **free in-home measure appointment** — no charge, no obligation.
- Final price depends on room size, product choice, and installation — a specialist confirms after the measure.

## What the agent must never say

- Specific prices or dollar estimates
- Any discount other than exactly 40%
- Installation timelines or labour costs
- Financing or payment plans
- Product brands, stock, or availability
- Warranty details
- Any terms not in the assignment

---

## Tuning

| File | What to change |
|------|---------------|
| `.env` | Store name, agent name, sale headline, credentials |
| `app/services/conversation.py` | System prompt — persona, objection handling, guardrails |
| `app/services/google_calendar.py` | Slot hours (`SLOT_HOURS`), slot duration (`SLOT_DURATION`) |
| `app/core/config.py` | Defaults for all settings |
