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


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables():
    from app.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
