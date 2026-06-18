"""Database initialization script.

Run this to create all tables and seed default data without starting bots.
Usage: python init_db.py
"""
import asyncio
import logging
import sys

from database.connection import get_db_pool, close_db_pool, check_db_connection
from database.models import (
    SCHEMA_STATEMENTS,
    COLUMN_MIGRATIONS,
    TYPE_MIGRATIONS,
    SEED_CATEGORIES,
    SEED_MENU_ITEMS,
    SEED_MENU_IMAGES,
)
from database.repositories import UserRepository
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


async def init_database() -> None:
    """Initialize database: create tables, seed data, and default admin.
    
    This function is idempotent — safe to run multiple times.
    """
    pool = await get_db_pool()
    
    # Create schema (one statement per call for asyncpg compatibility)
    logger.info("Creating database schema...")
    async with pool.acquire() as conn:
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)
    logger.info(f"Schema initialized ({len(SCHEMA_STATEMENTS)} statements).")
    
    # Apply column-level migrations for existing databases (idempotent).
    logger.info("Applying column migrations...")
    async with pool.acquire() as conn:
        for table, column, alter_sql in COLUMN_MIGRATIONS:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = $2)",
                table, column,
            )
            if not exists:
                await conn.execute(alter_sql)
                logger.info(f"Added column '{column}' to table '{table}'.")
    logger.info(f"Column migrations checked ({len(COLUMN_MIGRATIONS)} entries).")
    
    # Apply type-level migrations (idempotent: ALTER TYPE is a no-op if matched).
    logger.info("Applying type migrations...")
    async with pool.acquire() as conn:
        for table, column, alter_sql in TYPE_MIGRATIONS:
            await conn.execute(alter_sql)
    logger.info(f"Type migrations applied ({len(TYPE_MIGRATIONS)} entries).")
    
    # Seed categories
    logger.info("Seeding categories...")
    async with pool.acquire() as conn:
        for cat_id, name in SEED_CATEGORIES:
            await conn.execute(
                "INSERT INTO categories (id, name) VALUES ($1, $2) "
                "ON CONFLICT (id) DO NOTHING",
                cat_id, name,
            )
    
    # Count categories
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM categories")
    logger.info(f"Categories: {count} rows.")
    
    # Seed menu items
    logger.info("Seeding menu items...")
    async with pool.acquire() as conn:
        for item in SEED_MENU_ITEMS:
            await conn.execute(
                "INSERT INTO menu (id, name, description, price, category_id) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
                *item,
            )
    
    # Count menu items
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM menu")
    logger.info(f"Menu items: {count} rows.")
    
    # Seed menu item photos (UPDATE existing rows with image_url).
    logger.info("Seeding menu item photos...")
    async with pool.acquire() as conn:
        for item_id, image_url in SEED_MENU_IMAGES.items():
            await conn.execute(
                "UPDATE menu SET image_url = $1 WHERE id = $2",
                image_url, item_id,
            )
    logger.info(f"Menu photos seeded ({len(SEED_MENU_IMAGES)} entries).")
    
    # Ensure default admin exists
    user_repo = UserRepository(pool)
    await user_repo.ensure_admin_exists("admin", "password123")
    
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM users")
    logger.info(f"Users: {count} rows.")
    
    logger.info("=" * 50)
    logger.info("Database initialization complete!")
    logger.info("=" * 50)


async def main() -> None:
    """Main entry point."""
    setup_logging()
    
    logger.info("=" * 50)
    logger.info("Tokio Bar Database Initialization")
    logger.info("=" * 50)
    
    if not await check_db_connection():
        logger.error("Cannot connect to database. Check .env settings.")
        sys.exit(1)
    
    try:
        await init_database()
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())