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
from database.redis_connection import (
    get_redis,
    close_redis,
    check_redis_connection,
)
from database.migrations import bootstrap_database
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
from middlewares.throttling_middleware import ThrottlingMiddleware
from services import (
    AuthService,
    CartService,
    GuestSessionService,
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
        from utils.proxy_session import ProxyAwareAiohttpSession
        session = ProxyAwareAiohttpSession(proxy=proxy_url)
        logger.info(f"Using ProxyAwareAiohttpSession with proxy: {proxy_url}")
        return Bot(
            token=token,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
    
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


async def _create_fsm_storage():
    """Create the FSM storage backend.
    
    Uses aiogram's ``RedisStorage`` when Redis is available so FSM state/data
    survives restarts and is shared across instances. Falls back to
    ``MemoryStorage`` otherwise (development / single-instance mode).
    """
    redis = await get_redis()
    if redis is None:
        logger.info("FSM: using MemoryStorage (no Redis).")
        return MemoryStorage()
    try:
        from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder

        storage = RedisStorage(
            redis=redis,
            key_builder=DefaultKeyBuilder(with_bot_id=True),
            state_ttl=settings.redis_fsm_state_ttl,
            data_ttl=settings.redis_fsm_data_ttl,
        )
        logger.info("FSM: using RedisStorage (distributed mode).")
        return storage
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to initialise RedisStorage (%s). Falling back to "
            "MemoryStorage.", exc,
        )
        return MemoryStorage()


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
    
    table_service = TableService(
        assignment_repo, cart_repo, user_repo, closed_bill_repo
    )
    return {
        "auth_service": AuthService(user_repo),
        "menu_service": MenuService(menu_repo),
        "cart_service": CartService(cart_repo, menu_repo),
        "order_service": OrderService(order_repo, cart_repo),
        "table_service": table_service,
        "guest_session_service": GuestSessionService(table_service),
    }


def setup_guest_bot(services: dict, fsm_storage) -> tuple[Bot, Dispatcher]:
    """Configure the guest bot.
    
    Args:
        services: Dictionary of service instances.
        fsm_storage: FSM storage backend (Redis or Memory).
        
    Returns:
        Tuple of (Bot, Dispatcher) for the guest bot.
    """
    bot = _create_bot(settings.guest_bot_token)
    dp = Dispatcher(storage=fsm_storage)
    
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(ServiceMiddleware(**services))
    dp.callback_query.middleware(ServiceMiddleware(**services))
    dp.include_router(create_guest_router())
    
    return bot, dp


def setup_staff_bot(services: dict, fsm_storage) -> tuple[Bot, Dispatcher]:
    """Configure the staff bot.
    
    Args:
        services: Dictionary of service instances.
        fsm_storage: FSM storage backend (Redis or Memory).
        
    Returns:
        Tuple of (Bot, Dispatcher) for the staff bot.
    """
    bot = _create_bot(settings.staff_bot_token)
    dp = Dispatcher(storage=fsm_storage)
    
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
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
    
    # Initialize database (Alembic migrations + seed data).
    # Implementation lives in database/migrations.py (shared with init_db.py).
    await bootstrap_database()
    
    # Create services
    pool = await get_db_pool()
    services = create_services(pool)

    # Initialize Redis (sessions + FSM). Soft-fail to in-memory mode.
    redis_ok = await check_redis_connection()
    if redis_ok:
        logger.info("Redis is available — sessions and FSM use Redis.")
    else:
        logger.info("Redis is NOT available — using in-memory sessions/FSM.")

    # Resolve the shared FSM storage once (used by both dispatchers).
    fsm_storage = await _create_fsm_storage()

    # Setup bots
    guest_bot, guest_dp = setup_guest_bot(services, fsm_storage)
    staff_bot, staff_dp = setup_staff_bot(services, fsm_storage)
    
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
        """Run both bots.
        
        The initial ``delete_webhook`` calls are issued sequentially to avoid
        concurrent TLS handshakes through the proxy, which can cause
        ``ConnectionResetError`` on some HTTP proxies. After both webhooks are
        cleared, polling runs concurrently.
        """
        # 1. Sequential startup (avoids proxy connection storms)
        await run_bot_startup(guest_bot, guest_dp, "Guest")
        await run_bot_startup(staff_bot, staff_dp, "Staff")

        # 2. Concurrent polling
        await asyncio.gather(
            guest_dp.start_polling(guest_bot, allowed_updates=guest_dp.resolve_used_update_types()),
            staff_dp.start_polling(staff_bot, allowed_updates=staff_dp.resolve_used_update_types()),
        )

    async def run_bot_startup(bot: Bot, dp: Dispatcher, name: str) -> None:
        """Issue the initial delete_webhook for a bot."""
        try:
            logger.info(f"Starting {name} bot (clearing webhook)...")
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.error(f"{name} bot startup error: {e}", exc_info=True)

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
        logger.info("Database pool closed.")
        await close_redis()
        logger.info("Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)