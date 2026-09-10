"""
Vercel serverless entrypoint.

Vercel's Python runtime discovers functions under api/ and serves whatever ASGI
application the module exposes as `app`. vercel.json routes every path here, so
this one function handles the whole site — the marketing page, the dashboard and
all of the API routes — exactly as uvicorn does locally.

The repo root has to be on sys.path because Vercel executes this file directly
rather than as part of an installed package, so `import app...` would otherwise
fail to resolve.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app as fastapi_app  # noqa: E402

# Path this function is deployed at. If a request arrives with exactly this
# path, routing collapsed the original URL into the destination and FastAPI
# would 404 on everything.
_FUNCTION_PATH = "/api/index"

# Headers Vercel has used to carry the pre-rewrite path. Tried in order; the
# first one that looks like a real request path wins.
_ORIGINAL_PATH_HEADERS = (
    "x-vercel-original-path",
    "x-original-path",
    "x-matched-path",
    "x-vercel-original-pathname",
)


async def _send_json(send, payload, status=200):
    body = json.dumps(payload, indent=2).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")],
    })
    await send({"type": "http.response.body", "body": body})


class VercelASGIAdapter:
    """
    Keeps the app routable no matter how the platform delivers the path.

    Vercel changed internal rewrites to route on the rewritten destination, so a
    catch-all pointing at this function made every request arrive as
    "/api/index" and FastAPI 404'd the entire site. vercel.json now uses the
    path-preserving `routes` form; this restores the original path from a header
    if that ever stops holding, rather than silently serving 404s again.

    Append ?__diag=1 to any URL to see what this function actually received —
    a query string survives every form of path rewriting, so the diagnostic
    stays reachable even when routing is broken.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        received_path = scope.get("path", "")

        if b"__diag=1" in scope.get("query_string", b""):
            return await _send_json(send, {
                "received_path": received_path,
                "would_route_to": self._recover(received_path, headers) or received_path,
                "candidate_headers": {
                    h: headers.get(h) for h in _ORIGINAL_PATH_HEADERS if h in headers
                },
                "vercel_headers": {k: v for k, v in headers.items() if k.startswith("x-vercel")},
                "python": sys.version.split()[0],
            })

        recovered = self._recover(received_path, headers)
        if recovered:
            scope = dict(scope, path=recovered, raw_path=recovered.encode())

        await self.app(scope, receive, send)

    @staticmethod
    def _recover(path, headers):
        if path.rstrip("/") != _FUNCTION_PATH:
            return None                      # path arrived intact — nothing to do
        for name in _ORIGINAL_PATH_HEADERS:
            value = (headers.get(name) or "").split("?")[0]
            if value.startswith("/") and value.rstrip("/") != _FUNCTION_PATH:
                return value
        return "/"                           # fall back to the landing page


app = VercelASGIAdapter(fastapi_app)
