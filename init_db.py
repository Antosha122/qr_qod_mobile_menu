"""Database initialization script.

Run this to apply all migrations and seed default data without starting the
bots. It is a thin wrapper around the shared ``bootstrap_database`` routine in
``database/migrations.py`` — the same routine ``main.py`` uses at startup — so
there is exactly one implementation of the initialisation logic (DRY).

Usage:
    python init_db.py
"""
import asyncio
import logging
import sys

from database.connection import check_db_connection, close_db_pool
from database.migrations import bootstrap_database
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    """Apply migrations + seed data, then report basic row counts."""
    setup_logging()

    logger.info("=" * 50)
    logger.info("Tokio Bar Database Initialization")
    logger.info("=" * 50)

    if not await check_db_connection():
        logger.error("Cannot connect to database. Check .env settings.")
        sys.exit(1)

    try:
        # Shared bootstrap: Alembic migrations + seeding + admin + password hash.
        await bootstrap_database()

        # Friendly summary for manual runs.
        from database.connection import get_db_pool

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            cats = await conn.fetchval("SELECT COUNT(*) FROM categories")
            menu = await conn.fetchval("SELECT COUNT(*) FROM menu")
            users = await conn.fetchval("SELECT COUNT(*) FROM users")
        logger.info("Summary — categories: %s, menu items: %s, users: %s.", cats, menu, users)

        logger.info("=" * 50)
        logger.info("Database initialization complete!")
        logger.info("=" * 50)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())