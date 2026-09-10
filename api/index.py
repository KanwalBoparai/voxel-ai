"""
Vercel serverless entrypoint.

Vercel's Python runtime discovers functions under api/ and serves whatever ASGI
application the module exposes as `app`. vercel.json routes every path here with
the path-preserving `routes` form, so this one function handles the whole site —
the marketing page, the dashboard and all of the API routes — exactly as uvicorn
does locally.

Note the `routes` form matters: with `rewrites`, Vercel discards the original URL
and the app receives the literal string "/api/index", which matches no route and
404s the entire site.

The repo root has to be on sys.path because Vercel executes this file directly
rather than as part of an installed package, so `import app...` would otherwise
fail to resolve.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app  # noqa: E402,F401
