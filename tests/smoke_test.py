"""
Offline smoke tests — no API keys or network required.

Verifies: app boots, SQLite schema creates, demo page renders,
control-token parsing covers all outcomes, initial history shape.

Run:
  python tests/smoke_test.py
"""
import os
import sys

# Add the project root to sys.path so `app.*` imports work when the test is
# invoked directly (python tests/smoke_test.py) from any working directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./smoke_test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app                   # noqa: E402
from app.services import conversation      # noqa: E402
from app.services.agent_tools import TOOL_DEFINITIONS  # noqa: E402


def test_control_token_parsing():
    rx = conversation._CONTROL_RE
    cases = {
        "You're booked for Saturday! [[BOOK: Saturday 10:00 AM]]": ("BOOK", "Saturday 10:00 AM"),
        "Let me connect you. [[TRANSFER]]":                          ("TRANSFER", ""),
        "Thanks, take care! [[END]]":                                ("END", ""),
        "I'll note your interest. [[INTERESTED]]":                   ("INTERESTED", ""),
        "I'll call you back. [[CALLBACK: Sunday afternoon]]":        ("CALLBACK", "Sunday afternoon"),
        "No problem at all. [[NOT_INTERESTED]]":                     ("NOT_INTERESTED", ""),
        "You've been removed. [[DO_NOT_CALL]]":                      ("DO_NOT_CALL", ""),
        "Sorry for the mix-up. [[WRONG_NUMBER]]":                    ("WRONG_NUMBER", ""),
        "I'll try again later. [[BAD_TIMING]]":                      ("BAD_TIMING", ""),
        "Just a normal reply with no command.":                       (None, None),
    }
    for text, (want_action, want_detail) in cases.items():
        m = rx.search(text)
        if want_action is None:
            assert m is None, f"unexpected match in: {text!r}"
        else:
            assert m, f"no match in: {text!r}"
            assert m.group(1).upper() == want_action, f"{text!r}: got {m.group(1)!r}"
            assert (m.group(2) or "").strip() == want_detail, f"{text!r}"
    print("  control-token parsing — all 9 outcomes")


def test_tool_definitions():
    names = {t["name"] for t in TOOL_DEFINITIONS}
    assert names == {"check_available_slots", "book_measure_appointment", "save_call_outcome"}
    for tool in TOOL_DEFINITIONS:
        assert "description" in tool
        assert "input_schema" in tool
    print("  tool definitions — 3 tools, all have description + schema")


def test_initial_history_shape():
    # With known name and phone
    h = conversation.initial_history("Jordan", customer_phone="+14165550001")
    assert h and h[0]["role"] == "user"
    assert "Jordan" in h[0]["content"]
    assert "+14165550001" in h[0]["content"]

    # Without name — must not address customer by name
    h2 = conversation.initial_history("")
    assert "do NOT know" in h2[0]["content"]
    print("  initial_history — name-known and name-unknown paths")


def test_app_boots_and_endpoints():
    with TestClient(app) as client:
        # Health check
        assert client.get("/health").json() == {"status": "ok"}

        # Demo page renders with store name
        demo = client.get("/demo")
        assert demo.status_code == 200
        assert "Maple Carpet" in demo.text or "Voice Agent" in demo.text

        # Tool webhook exists
        r = client.post("/tools/vapi", json={"message": {"toolCallList": []}})
        assert r.status_code == 200
        assert r.json() == {"results": []}

        # Invalid phone rejected cleanly (no real API needed)
        r = client.post("/demo/call", json={"phone": "not-a-number", "name": "Test"})
        assert r.status_code == 400

    print("  app boots — /health, /demo, /tools/vapi, input validation")


if __name__ == "__main__":
    print("Running smoke tests...\n")
    failed = False
    for fn in [
        test_control_token_parsing,
        test_tool_definitions,
        test_initial_history_shape,
        test_app_boots_and_endpoints,
    ]:
        try:
            fn()
        except AssertionError as e:
            print(f"  FAILED: {fn.__name__} — {e}")
            failed = True

    print()
    if failed:
        print("Some tests failed.")
        sys.exit(1)
    print("All smoke tests passed.")
