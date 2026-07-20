#!/bin/bash
set -e

echo "=== Voxel AI — Voice Agent Platform Setup ==="

# 1. Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env from example
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "Created .env — fill in your keys before running."
fi

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Fill in .env (minimum: ANTHROPIC_API_KEY)"
echo ""
echo "2. Configure your business in config/business.json"
echo "   (or copy one from config/examples/ — dental, law firm, restaurant, etc.)"
echo ""
echo "3. Start the server:"
echo "   source .venv/bin/activate && uvicorn app.main:app --reload"
echo ""
echo "4. Open the app:"
echo "   http://localhost:8000            (landing page)"
echo "   http://localhost:8000/demo       (live voice demo, no phone needed)"
echo "   http://localhost:8000/dashboard  (business owner dashboard)"
echo ""
echo "5. Run smoke tests:"
echo "   python tests/smoke_test.py"
echo ""
echo "6. To place a real call (requires VAPI_API_KEY + VAPI_PHONE_NUMBER_ID in .env):"
echo "   python vapi_call.py \"+1 628 555 0100\" \"Jordan\""
echo ""
echo "See RUNBOOK.md for full setup including Google Calendar and CRM."
