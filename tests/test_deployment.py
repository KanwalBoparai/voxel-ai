"""
Regression tests for the deployment failures this app has actually hit.

Every case here was a real outage on a serverless host, and none of them
reproduce under a plain `uvicorn app.main:app` — the conditions (no ASGI
lifespan, read-only working directory, a provider-shaped database URL) only
show up once deployed. They are cheap to assert and expensive to rediscover.
"""
import os

import httpx
import pytest


# ── database URLs ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "given,expected",
    [
        # Managed providers hand out sync-driver URLs; the async engine needs
        # an explicit driver or it refuses to build.
        ("postgresql://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgres://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        # asyncpg rejects sslmode — that's a psycopg2 parameter.
        ("postgresql://u:p@host/db?sslmode=require", "postgresql+asyncpg://u:p@host/db"),
        # Already-correct and SQLite URLs pass through untouched.
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("sqlite+aiosqlite:///./voxel_ai.db", "sqlite+aiosqlite:///./voxel_ai.db"),
    ],
)
def test_database_urls_are_normalised_for_the_async_engine(given, expected):
    from app.db.database import normalize_db_url

    assert normalize_db_url(given) == expected


def test_sslmode_stripped_but_other_params_kept():
    from app.db.database import normalize_db_url

    out = normalize_db_url("postgresql://u:p@h/db?sslmode=require&application_name=voxel")
    assert "sslmode" not in out
    assert "application_name=voxel" in out


def test_sqlite_relocates_when_its_directory_is_read_only(tmp_path):
    """
    The zero-setup default is a relative SQLite path, which lands in the
    deployment directory — read-only on a serverless host. The error surfaces
    at first query, not at startup, so every data endpoint 503s.
    """
    from app.db.database import relocate_unwritable_sqlite

    readonly = tmp_path / "ro"
    readonly.mkdir()
    os.chmod(readonly, 0o555)
    try:
        url = relocate_unwritable_sqlite(f"sqlite+aiosqlite:///{readonly}/voxel.db")
        assert url.endswith("/tmp/voxel.db"), url
    finally:
        os.chmod(readonly, 0o755)


def test_writable_sqlite_is_left_alone(tmp_path):
    from app.db.database import relocate_unwritable_sqlite

    original = f"sqlite+aiosqlite:///{tmp_path}/voxel.db"
    assert relocate_unwritable_sqlite(original) == original


def test_non_sqlite_urls_are_never_relocated():
    from app.db.database import relocate_unwritable_sqlite

    url = "postgresql+asyncpg://u:p@host/db"
    assert relocate_unwritable_sqlite(url) == url


# ── booting under hostile conditions ─────────────────────────────────────────

async def _get(paths, **env):
    """Drive the app with no lifespan events — how a serverless host invokes it."""
    for key, value in env.items():
        os.environ[key] = value
    for module in [m for m in list(__import__("sys").modules) if m.startswith("app.")]:
        del __import__("sys").modules[module]

    from app.main import app

    results = {}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        for path in paths:
            results[path] = (await client.get(path)).status_code
    return results


@pytest.mark.asyncio
async def test_app_serves_without_lifespan_or_a_configured_database():
    """
    Vercel does not run ASGI lifespan events, so the startup hook that creates
    tables never fires. Schema creation hangs off the first session instead;
    without that, every database-backed endpoint returned 500.
    """
    codes = await _get(
        ["/health", "/", "/dashboard", "/api/customers", "/api/dashboard/overview"],
        DATABASE_URL="sqlite+aiosqlite:////tmp/voxel_test_boot.db",
    )
    assert codes == dict.fromkeys(codes, 200), codes


@pytest.mark.asyncio
async def test_pages_still_serve_when_the_database_is_unreachable():
    """
    A database that is down must not take the whole site with it. Data
    endpoints report 503; pages and /health keep working.
    """
    codes = await _get(
        ["/health", "/", "/api/customers"],
        DATABASE_URL="postgresql://u:p@127.0.0.1:1/db",
    )
    assert codes["/health"] == 200
    assert codes["/"] == 200
    assert codes["/api/customers"] == 503
