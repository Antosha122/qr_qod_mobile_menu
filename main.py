"""Main application entry point.

Starts both the guest bot and the staff bot concurrently using asyncio.
Supports proxy configuration for regions where Telegram API is blocked/unstable.
"""
import asyncio
import logging
import signal
import sys
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import settings
from database.connection import get_db_pool, close_db_pool, check_db_connection
from database.models import (
    SCHEMA_STATEMENTS,
    COLUMN_MIGRATIONS,
    TYPE_MIGRATIONS,
    SEED_CATEGORIES,
    SEED_MENU_ITEMS,
    SEED_MENU_IMAGES,
)
from database.repositories import (
    UserRepository,
    MenuRepository,
    CartRepository,
    OrderRepository,
    WaiterAssignmentRepository,
    ClosedBillRepository,
)
from middlewares.service_middleware import ServiceMiddleware
from middlewares.auth_middleware import StaffAuthMiddleware
from services import (
    AuthService,
    CartService,
    MenuService,
    OrderService,
    TableService,
)
from utils.logger import setup_logging
from handlers import create_guest_router, create_staff_router

logger = logging.getLogger(__name__)


def _create_bot(token: str) -> Bot:
    """Create a Bot instance, optionally with proxy support.
    
    Args:
        token: Bot API token.
        
    Returns:
        Bot instance, with proxy configured if PROXY_URL is set in settings.
    """
    proxy_url = settings.proxy_url.strip() if settings.proxy_url else ""
    
    if proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession
        session = AiohttpSession(proxy=proxy_url)
        logger.info(f"Using proxy: {proxy_url}")
        return Bot(
            token=token,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
    
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


async def init_database() -> None:
    """Initialize database: create pool, schema, seed data, and default admin.
    
    This function is idempotent — safe to run multiple times.
    Creates all tables if they don't exist and seeds default menu data.
    """
    pool = await get_db_pool()
    
    # Create schema — asyncpg requires one statement per execute() call
    async with pool.acquire() as conn:
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)
    logger.info(f"Database schema initialized ({len(SCHEMA_STATEMENTS)} statements).")
    
    # Apply column-level migrations for existing databases (idempotent).
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
    async with pool.acquire() as conn:
        for table, column, alter_sql in TYPE_MIGRATIONS:
            await conn.execute(alter_sql)
    logger.info(f"Type migrations applied ({len(TYPE_MIGRATIONS)} entries).")
    
    # Seed categories (idempotent — ON CONFLICT DO NOTHING)
    async with pool.acquire() as conn:
        for cat_id, name in SEED_CATEGORIES:
            await conn.execute(
                "INSERT INTO categories (id, name) VALUES ($1, $2) "
                "ON CONFLICT (id) DO NOTHING",
                cat_id, name,
            )
    logger.info(f"Categories seeded ({len(SEED_CATEGORIES)} entries).")
    
    # Seed menu items (idempotent)
    async with pool.acquire() as conn:
        for item in SEED_MENU_ITEMS:
            await conn.execute(
                "INSERT INTO menu (id, name, description, price, category_id) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
                *item,
            )
    logger.info(f"Menu items seeded ({len(SEED_MENU_ITEMS)} entries).")
    
    # Seed menu item photos (UPDATE existing rows with image_url).
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
    logger.info("Default admin account verified.")


def create_services(pool) -> dict:
    """Create all service instances with their repositories.
    
    Args:
        pool: Database connection pool.
        
    Returns:
        Dictionary of service instances.
    """
    user_repo = UserRepository(pool)
    menu_repo = MenuRepository(pool)
    cart_repo = CartRepository(pool)
    order_repo = OrderRepository(pool)
    assignment_repo = WaiterAssignmentRepository(pool)
    closed_bill_repo = ClosedBillRepository(pool)
    
    return {
        "auth_service": AuthService(user_repo),
        "menu_service": MenuService(menu_repo),
        "cart_service": CartService(cart_repo, menu_repo),
        "order_service": OrderService(order_repo, cart_repo),
        "table_service": TableService(
            assignment_repo, cart_repo, user_repo, closed_bill_repo
        ),
    }


def setup_guest_bot(services: dict) -> tuple[Bot, Dispatcher]:
    """Configure the guest bot.
    
    Args:
        services: Dictionary of service instances.
        
    Returns:
        Tuple of (Bot, Dispatcher) for the guest bot.
    """
    bot = _create_bot(settings.guest_bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.message.middleware(ServiceMiddleware(**services))
    dp.callback_query.middleware(ServiceMiddleware(**services))
    dp.include_router(create_guest_router())
    
    return bot, dp


def setup_staff_bot(services: dict) -> tuple[Bot, Dispatcher]:
    """Configure the staff bot.
    
    Args:
        services: Dictionary of service instances.
        
    Returns:
        Tuple of (Bot, Dispatcher) for the staff bot.
    """
    bot = _create_bot(settings.staff_bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.message.middleware(ServiceMiddleware(**services))
    dp.message.middleware(StaffAuthMiddleware())
    dp.callback_query.middleware(ServiceMiddleware(**services))
    dp.callback_query.middleware(StaffAuthMiddleware())
    dp.include_router(create_staff_router())
    
    return bot, dp


async def run_bot(bot: Bot, dp: Dispatcher, name: str) -> None:
    """Run a single bot with polling, handling errors gracefully.
    
    Args:
        bot: Bot instance.
        dp: Dispatcher instance.
        name: Bot name for logging.
    """
    try:
        logger.info(f"Starting {name} bot polling...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"{name} bot error: {e}", exc_info=True)
    finally:
        await bot.session.close()


async def main() -> None:
    """Main entry point: initialize and run both bots."""
    setup_logging()
    
    logger.info("=" * 50)
    logger.info("Starting Tokio Bar Restaurant System")
    logger.info("=" * 50)
    
    # Check database connection
    if not await check_db_connection():
        logger.error("Cannot connect to database. Exiting.")
        return
    
    # Initialize database (create tables + seed data)
    await init_database()
    
    # Create services
    pool = await get_db_pool()
    services = create_services(pool)
    
    # Setup bots
    guest_bot, guest_dp = setup_guest_bot(services)
    staff_bot, staff_dp = setup_staff_bot(services)
    
    logger.info("Both bots configured. Starting polling...")
    
    # Graceful shutdown via SIGTERM/SIGINT (Docker sends SIGTERM on `stop`).
    shutdown_event = asyncio.Event()

    def _request_shutdown() -> None:
        logger.info("Received shutdown signal, initiating graceful shutdown...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    # SIGINT (Ctrl-C) and SIGTERM (Docker stop) → clean exit.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except (NotImplementedError, RuntimeError):
            # Windows does not support add_signal_handler → fallback to signal().
            def _sig_handler(signum, frame, _fn=_request_shutdown):
                _fn()
            signal.signal(sig, _sig_handler)

    async def _run_bots() -> None:
        """Run both bots concurrently."""
        await asyncio.gather(
            run_bot(guest_bot, guest_dp, "Guest"),
            run_bot(staff_bot, staff_dp, "Staff"),
        )

    try:
        bot_task = asyncio.create_task(_run_bots())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # Wait for either: bots finish naturally OR a shutdown signal arrives.
        await asyncio.wait(
            {bot_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not bot_task.done():
            logger.info("Stopping bot polling (graceful shutdown)...")
            await guest_dp.stop_polling()
            await staff_dp.stop_polling()
            bot_task.cancel()
            try:
                await bot_task
            except (asyncio.CancelledError, Exception):
                pass

        # Clean up the shutdown watcher so we don't leave a dangling task.
        if not shutdown_task.done():
            shutdown_task.cancel()
            try:
                await shutdown_task
            except asyncio.CancelledError:
                pass
    finally:
        await close_db_pool()
        logger.info("Database pool closed. Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
