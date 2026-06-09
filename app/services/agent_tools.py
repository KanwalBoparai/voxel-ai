"""
Tool definitions for Claude tool use + a shared executor.

The same tools are used in two places:
  1. Text demo (/demo/chat) — Claude calls them directly via the Anthropic tool-use API.
  2. Vapi calls            — Vapi POSTs to /tools/vapi-webhook; we execute and return.
"""
import json
from app.services import google_calendar, google_sheets

# ── tool schemas (passed to claude messages.create) ──────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "check_available_slots",
        "description": (
            "Check the shared appointment calendar and return available free in-home "
            "measure slots for this weekend. Call this when the customer expresses "
            "interest in booking and states a preferred day or time range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_day": {
                    "type": "string",
                    "description": "Saturday or Sunday",
                },
                "preferred_time_range": {
                    "type": "string",
                    "description": "morning, afternoon, or empty if not stated",
                },
                "customer_phone": {
                    "type": "string",
                    "description": "Customer phone number",
                },
            },
            "required": ["preferred_day"],
        },
    },
    {
        "name": "book_measure_appointment",
        "description": (
            "Book the selected free in-home measure appointment in the shared calendar. "
            "Only call this after the customer has confirmed a specific slot AND provided "
            "their address. Do not book any other type of service."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name":    {"type": "string"},
                "customer_phone":   {"type": "string"},
                "appointment_date": {"type": "string", "description": "e.g. Saturday"},
                "appointment_time": {"type": "string", "description": "e.g. 10:00 AM"},
                "customer_address": {
                    "type": "string",
                    "description": "Full address the specialist should visit",
                },
                "notes": {"type": "string"},
            },
            "required": [
                "customer_name", "customer_phone",
                "appointment_date", "appointment_time", "customer_address",
            ],
        },
    },
    {
        "name": "save_call_outcome",
        "description": (
            "Save the final call result to the CRM. Call this at the end of EVERY call "
            "regardless of outcome. Allowed outcomes: booked, interested, not_interested, "
            "callback, do_not_call, voicemail, wrong_number, bad_timing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name":    {"type": "string"},
                "customer_phone":   {"type": "string"},
                "outcome": {
                    "type": "string",
                    "enum": [
                        "booked", "interested", "not_interested",
                        "callback", "do_not_call", "voicemail",
                        "wrong_number", "bad_timing",
                    ],
                },
                "appointment_date": {"type": "string"},
                "appointment_time": {"type": "string"},
                "customer_address": {"type": "string"},
                "callback_time":    {"type": "string"},
                "notes":            {"type": "string"},
                "do_not_call": {
                    "type": "boolean",
                    "description": "true only when customer explicitly asked to be removed",
                },
            },
            "required": ["customer_name", "customer_phone", "outcome"],
        },
    },
]


# ── shared executor ───────────────────────────────────────────────────────────

async def execute_tool(name: str, inputs: dict) -> str:
    """Run a tool by name; returns a JSON string suitable for tool_result content."""
    try:
        if name == "check_available_slots":
            result = await google_calendar.check_available_slots(
                preferred_day=inputs.get("preferred_day", ""),
                preferred_time_range=inputs.get("preferred_time_range", ""),
                customer_phone=inputs.get("customer_phone", ""),
            )
        elif name == "book_measure_appointment":
            result = await google_calendar.book_measure_appointment(
                customer_name=inputs.get("customer_name", ""),
                customer_phone=inputs.get("customer_phone", ""),
                appointment_date=inputs.get("appointment_date", ""),
                appointment_time=inputs.get("appointment_time", ""),
                customer_address=inputs.get("customer_address", ""),
                notes=inputs.get("notes", ""),
            )
        elif name == "save_call_outcome":
            result = await google_sheets.save_call_outcome(
                customer_name=inputs.get("customer_name", ""),
                customer_phone=inputs.get("customer_phone", ""),
                outcome=inputs.get("outcome", "not_interested"),
                appointment_date=inputs.get("appointment_date", ""),
                appointment_time=inputs.get("appointment_time", ""),
                customer_address=inputs.get("customer_address", ""),
                callback_time=inputs.get("callback_time", ""),
                notes=inputs.get("notes", ""),
                do_not_call=inputs.get("do_not_call", False),
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        result = {"error": str(exc)}

    return json.dumps(result)
