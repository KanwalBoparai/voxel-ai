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


engine = create_async_engine(normalize_db_url(settings.DATABASE_URL), echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables():
    from app.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
