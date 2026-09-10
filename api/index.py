"""
Vercel serverless entrypoint.

Vercel's Python runtime discovers functions under api/ and serves whatever ASGI
application the module exposes as `app`. vercel.json rewrites every path here,
so this one function handles the whole site — the marketing page, the dashboard
and all of the API routes — exactly as uvicorn does locally.

The repo root has to be on sys.path because Vercel executes this file directly
rather than as part of an installed package, so `import app...` would otherwise
fail to resolve.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app  # noqa: E402,F401
