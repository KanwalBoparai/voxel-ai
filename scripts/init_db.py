"""
Create the database schema. Run once against a new database.

Serverless deploys set AUTO_CREATE_TABLES=false so the schema check doesn't run
on every cold start, which means the tables have to be created out of band:

    DATABASE_URL='postgresql://user:pass@host/db' python scripts/init_db.py

Safe to re-run — create_all() only adds tables that are missing. It does not
alter existing ones, so a column added to app/db/models.py later needs a real
migration rather than another run of this script.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.database import create_tables, normalize_db_url  # noqa: E402
from app.core.config import settings  # noqa: E402


async def main() -> None:
    url = normalize_db_url(settings.DATABASE_URL)
    # Never print the password back out.
    safe = url.split("@")[-1] if "@" in url else url
    print(f"Creating schema on {safe} ...")
    await create_tables()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
