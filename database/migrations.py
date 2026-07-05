"""Database bootstrap logic — single source of truth for app startup.

Previously the database initialisation logic (schema creation + migrations +
seeding + admin bootstrap) was duplicated in ``main.py`` and ``init_db.py``.
It now lives here so both entry points share one implementation (DRY).

Responsibilities:
    1. Apply schema migrations via Alembic (``upgrade head``).
    2. Seed default categories / menu items / images (idempotent).
    3. Ensure the default admin account exists.
    4. Hash any legacy plain-text passwords.

Schema DDL is no longer defined here — Alembic owns it (``alembic/versions/``).
"""
import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from config.settings import settings
from database.connection import get_db_pool
from database.models import (
    SEED_CATEGORIES,
    SEED_MENU_ITEMS,
    SEED_MENU_IMAGES,
)
from database.repositories import UserRepository
from migrate_passwords import migrate_passwords
from services import AuthService

logger = logging.getLogger(__name__)

# Absolute path to the project root (where alembic.ini lives).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"


def _make_alembic_config() -> AlembicConfig:
    """Build an Alembic ``Config`` bound to this project's ``alembic.ini``.

    The database URL is *not* set here — ``alembic/env.py`` resolves it from
    application settings at runtime.
    """
    if not _ALEMBIC_INI.exists():
        raise FileNotFoundError(f"alembic.ini not found at {_ALEMBIC_INI}")
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    # Ensure migration scripts are resolved relative to the project root.
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return cfg


def _alembic_upgrade_head() -> None:
    """Synchronously run ``alembic upgrade head``.

    Wraps Alembic's command API. Intended to be invoked from a worker thread
    (see :func:`apply_migrations`) because Alembic's own ``env.py`` bridges to
    asyncio via ``asyncio.run``, which cannot run inside an active event loop.
    """
    cfg = _make_alembic_config()
    command.upgrade(cfg, "head")


async def apply_migrations() -> None:
    """Apply all pending Alembic migrations.

    Runs the (synchronous) Alembic command in a background thread so that the
    current event loop — which is active when called from ``main.py`` — is not
    blocked and Alembic's internal ``asyncio.run`` works correctly.
    """
    await asyncio.to_thread(_alembic_upgrade_head)
    logger.info("Alembic migrations applied (upgrade head).")


async def _seed_categories() -> None:
    """Insert default categories (idempotent — ON CONFLICT DO NOTHING)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        for cat_id, name in SEED_CATEGORIES:
            await conn.execute(
                "INSERT INTO categories (id, name) VALUES ($1, $2) "
                "ON CONFLICT (id) DO NOTHING",
                cat_id, name,
            )
    logger.info("Categories seeded (%d entries).", len(SEED_CATEGORIES))


async def _seed_menu_items() -> None:
    """Insert default menu items (idempotent — ON CONFLICT DO NOTHING)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        for item in SEED_MENU_ITEMS:
            await conn.execute(
                "INSERT INTO menu (id, name, description, price, category_id) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
                *item,
            )
    logger.info("Menu items seeded (%d entries).", len(SEED_MENU_ITEMS))


async def _seed_menu_images() -> None:
    """Apply/refresh default menu item photos (idempotent UPDATE)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        for item_id, image_url in SEED_MENU_IMAGES.items():
            await conn.execute(
                "UPDATE menu SET image_url = $1 WHERE id = $2",
                image_url, item_id,
            )
    logger.info("Menu photos seeded (%d entries).", len(SEED_MENU_IMAGES))


async def _ensure_default_admin() -> None:
    """Create / verify the default admin account.

    If ``ADMIN_PASSWORD`` is unset, a random one-time password is generated,
    logged once, and the admin is forced to change it on first login.
    """
    pool = await get_db_pool()
    user_repo = UserRepository(pool)
    auth = AuthService(user_repo)
    one_time_password = await auth.ensure_admin_exists(
        username=settings.admin_username,
        password=settings.admin_password,
    )
    if one_time_password:
        logger.warning(
            "No ADMIN_PASSWORD was set. A one-time admin password was "
            "generated: %s — change it on first login!", one_time_password,
        )
    logger.info("Default admin account verified.")


async def bootstrap_database(*, with_seed: bool = True) -> None:
    """Initialise the database for application use.

    This is the single function called by both ``main.py`` and ``init_db.py``.
    It is idempotent and safe to run on every startup.

    Args:
        with_seed: When True (default), seed default categories / menu items /
            images and ensure the admin account exists. Set to False for a
            "schema-only" bootstrap (e.g. CI / test databases).
    """
    # 1. Schema migrations — Alembic owns all DDL.
    await apply_migrations()

    if not with_seed:
        return

    # 2. Seed reference data.
    await _seed_categories()
    await _seed_menu_items()
    await _seed_menu_images()

    # 3. Ensure the default admin exists.
    await _ensure_default_admin()

    # 4. Hash any legacy plain-text passwords (idempotent).
    migrated = await migrate_passwords()
    if migrated:
        logger.info(
            "Migrated %d legacy plain-text password(s) to bcrypt.", migrated,
        )


__all__ = ["apply_migrations", "bootstrap_database"]