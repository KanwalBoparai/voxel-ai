from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings


def normalize_db_url(url: str) -> str:
    """
    Make a hosted Postgres URL usable by SQLAlchemy's async engine.

    Managed providers (Render, Heroku, Neon, Supabase) hand out sync-driver
    URLs like `postgres://…` or `postgresql://…`, sometimes with a
    `?sslmode=require` suffix. create_async_engine() needs an explicit async
    driver, and asyncpg rejects `sslmode` (that's a psycopg2 parameter), so a
    pasted connection string would otherwise blow up at import time. SQLite and
    already-qualified URLs pass through untouched.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql"):
        return url

    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "sslmode"]
    return urlunsplit(
        ("postgresql+asyncpg", parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _build_engine():
    """
    Build the async engine without ever raising at import time.

    create_async_engine() validates the URL and resolves the driver eagerly, so
    a malformed DATABASE_URL — or one naming a driver that isn't installed —
    raises here, while this module is being imported. On a serverless host that
    means the function never loads at all and every request, including /health,
    comes back as a bare crash with nothing useful in the log. Falling back to a
    scratch SQLite file keeps the app importable so it can report the problem;
    endpoints that actually touch the database still fail loudly.
    """
    url = normalize_db_url(settings.DATABASE_URL)
    try:
        return create_async_engine(url, echo=False)
    except Exception as exc:
        print(f"[db] unusable DATABASE_URL ({exc}) — falling back to scratch SQLite")
        return create_async_engine("sqlite+aiosqlite:////tmp/voxel_fallback.db", echo=False)


engine = _build_engine()
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


_schema_checked = False


async def ensure_schema() -> None:
    """
    Create missing tables once per process, on first database use.

    main.py also does this from the lifespan hook, but serverless runtimes don't
    reliably run ASGI lifespan events — on Vercel they don't fire at all, so the
    tables were never created and every database-backed endpoint returned a 500.
    Hanging the check off the first session instead means it runs wherever the
    app is hosted.

    Deploys that manage their schema out of band set AUTO_CREATE_TABLES=false
    (see scripts/init_db.py). Failures are logged and not retried — a database
    that is down shouldn't add a failed DDL round-trip to every later request.
    """
    global _schema_checked
    if _schema_checked or not settings.AUTO_CREATE_TABLES:
        return
    _schema_checked = True
    try:
        await create_tables()
    except Exception as exc:
        print(f"[db] schema check failed: {exc}")


async def get_db():
    await ensure_schema()
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables():
    from app.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
