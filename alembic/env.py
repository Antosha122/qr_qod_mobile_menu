"""Alembic migration environment.

Resolves the database URL from the application's settings (``config.settings``)
so that migrations use the *same* ``.env``-driven configuration as the bot.

Supports both:
- **offline mode** (``alembic upgrade head --sql``) → emits SQL script.
- **online mode** (default) → runs migrations against the live database using
  an async SQLAlchemy engine backed by ``asyncpg``.
"""
import asyncio
import logging
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---- Alembic configuration --------------------------------------------------
config = context.config

# Configure Python logging from alembic.ini (if the section is present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ---- Application schema -----------------------------------------------------
# Import the metadata produced by the declarative models so Alembic can
# autogenerate migrations from them.
from database.db_schema import Base  # noqa: E402  (after config is set up)

target_metadata = Base.metadata

# ---- Resolve the database URL from application settings ---------------------
# settings.database_url returns a ``postgresql://`` URL; SQLAlchemy needs the
# ``+asyncpg`` driver suffix for the async engine used in online mode.
from config.settings import settings as _app_settings  # noqa: E402

_DB_URL_ASYNC = _app_settings.database_url.replace(
    "postgresql://", "postgresql+asyncpg://", 1,
)
config.set_main_option("sqlalchemy.url", _DB_URL_ASYNC)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to stdout rather than connecting to the database. The URL must
    use a sync-compatible driver for offline rendering of asyncpg DDL, so we
    strip the ``+asyncpg`` driver here.
    """
    url = config.get_main_option("sqlalchemy.url")
    if url and "+asyncpg:" in url:
        url = url.replace("+asyncpg", "")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure context for a live connection and run migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — bridges sync Alembic to async I/O."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()