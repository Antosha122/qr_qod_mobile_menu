"""Redis client management.

Provides a process-wide Redis client (``redis.asyncio.Redis``) used for:

  * staff authentication sessions (with TTL + explicit revoke), and
  * aiogram FSM storage (``RedisStorage`` instead of ``MemoryStorage``).

Design notes
------------
* When ``REDIS_URL`` is not configured, all functions degrade gracefully:
  ``get_redis()`` returns ``None`` and the rest of the app falls back to
  in-memory storage. This keeps local development & the test suite working
  without a running Redis instance.
* The connection is created lazily on first use and reused afterwards.
* ``close_redis()`` is called during application shutdown.
* ``check_redis_connection()`` is used by the startup probe and the Docker
  healthcheck to verify reachability. It is a *soft* check: a failure is
  logged but does NOT abort startup (the app falls back to in-memory mode).
"""
import logging
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

# Global Redis client (created lazily).
_redis: Optional["Redis"] = None  # type: ignore[name-defined]

# Set to True once we've determined Redis is unavailable so we don't spam
# the logs with connection attempts on every call.
_redis_disabled: bool = False


def _import_redis():
    """Import redis lazily so the app still boots if redis isn't installed."""
    try:
        import redis.asyncio as aioredis  # type: ignore

        return aioredis
    except ImportError:  # pragma: no cover — dependency is in requirements.txt
        logger.warning(
            "The 'redis' package is not installed. "
            "Falling back to in-memory sessions/FSM."
        )
        return None


async def get_redis():  # type: ignore[override]
    """Get or create the global async Redis client.

    Returns ``None`` when Redis is not configured or unreachable, in which
    case callers should use their in-memory fallback.
    """
    global _redis, _redis_disabled

    if _redis_disabled:
        return None

    if _redis is not None:
        return _redis

    if not settings.redis_url:
        logger.info(
            "REDIS_URL is not set — using in-memory sessions and FSM "
            "(single-instance mode)."
        )
        _redis_disabled = True
        return None

    aioredis = _import_redis()
    if aioredis is None:
        _redis_disabled = True
        return None

    try:
        # ``from_url`` accepts both ``redis://`` and ``rediss://`` (TLS).
        client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        # Ping once to fail fast on bad URLs / credentials.
        await client.ping()
        _redis = client
        logger.info("Redis connection established for sessions + FSM.")
        return _redis
    except Exception as exc:  # noqa: BLE001 — any failure → fallback
        logger.warning(
            "Redis connection failed (%s). Falling back to in-memory "
            "sessions/FSM. This is NOT safe for multi-instance deployments.",
            exc,
        )
        _redis_disabled = True
        return None


async def close_redis() -> None:
    """Close the Redis connection gracefully on shutdown."""
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        except Exception:  # noqa: BLE001 — best-effort close
            pass
        _redis = None
        logger.info("Redis connection closed.")


async def check_redis_connection() -> bool:
    """Verify that Redis is reachable.

    Returns ``False`` (not an error) when Redis is not configured — the app
    is allowed to run in in-memory mode. Returns ``True`` only when a
    configured Redis instance actually responds to ``PING``.
    """
    if not settings.redis_url:
        return False
    client = await get_redis()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis ping failed: %s", exc)
        return False