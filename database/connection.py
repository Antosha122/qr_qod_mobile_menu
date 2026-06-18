"""Database connection management using asyncpg connection pool."""
import logging
from typing import Optional

import asyncpg

from config.settings import settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create the database connection pool.
    
    Returns:
        asyncpg.Pool: The connection pool instance.
        
    Raises:
        asyncpg.PostgresError: If connection cannot be established.
    """
    global _pool
    if _pool is None:
        logger.info(
            "Creating database pool (min_size=%s, max_size=%s, command_timeout=%ss)...",
            settings.db_pool_min_size,
            settings.db_pool_max_size,
            settings.db_command_timeout,
        )
        _pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.db_command_timeout,
        )
        logger.info("Database connection pool created successfully.")
    return _pool


async def close_db_pool() -> None:
    """Close the database connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed.")


async def check_db_connection() -> bool:
    """Check if database connection is available.
    
    Returns:
        bool: True if connection is successful, False otherwise.
    """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False