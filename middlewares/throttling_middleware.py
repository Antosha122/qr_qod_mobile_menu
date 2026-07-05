"""Rate-limiting middleware to prevent abuse (brute-force, spam).

Uses Redis when available (distributed, shared across instances) or an
in-memory dict fallback (single-instance only). Limits are per-user per-key.

Typical keys: "login", "start", "cart", "checkout", etc.
"""
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from database.redis_connection import get_redis

logger = logging.getLogger(__name__)

# In-memory fallback: {(user_id, key): [timestamp, ...]}
_memory: Dict[tuple[int, str], list[float]] = {}

# Default rate limits per key (max calls, window_seconds).
DEFAULT_LIMITS: Dict[str, tuple[int, int]] = {
    "login": (5, 60),       # 5 attempts per minute
    "start": (10, 60),      # 10 /start per minute
    "cart": (30, 60),       # 30 cart actions per minute
    "checkout": (5, 60),    # 5 checkouts per minute
    "default": (20, 60),    # 20 generic actions per minute
}

REDIS_KEY_PREFIX = "tokio:throttle:"


async def _check_rate_limit(
    user_id: int,
    key: str,
    max_calls: int,
    window: int,
) -> bool:
    """Check if the user is within the rate limit.

    Returns True if the request is ALLOWED, False if it should be blocked.
    Uses Redis (sliding window) when available, in-memory dict otherwise.
    """
    redis = await get_redis()
    if redis is not None:
        try:
            now = time.time()
            rkey = f"{REDIS_KEY_PREFIX}{key}:{user_id}"
            # Remove timestamps older than the window.
            await redis.zremrangebyscore(rkey, 0, now - window)
            # Count current entries.
            count = await redis.zcard(rkey)
            if count >= max_calls:
                return False
            await redis.zadd(rkey, {str(now): now})
            await redis.expire(rkey, window)
            return True
        except Exception as exc:
            logger.warning("Redis throttle check failed: %s. Using in-memory.", exc)

    # In-memory fallback (sliding window).
    now = time.time()
    mem_key = (user_id, key)
    timestamps = _memory.get(mem_key, [])
    # Keep only timestamps within the window.
    timestamps = [ts for ts in timestamps if now - ts < window]
    if len(timestamps) >= max_calls:
        _memory[mem_key] = timestamps
        return False
    timestamps.append(now)
    _memory[mem_key] = timestamps
    return True


class ThrottlingMiddleware(BaseMiddleware):
    """Rate-limiting middleware.

    Usage::

        dp.message.middleware(ThrottlingMiddleware())
        dp.callback_query.middleware(ThrottlingMiddleware())

    The middleware inspects the handler's name or callback data to pick a
    rate-limit key (e.g. "login", "cart", "checkout"). Requests exceeding the
    limit are silently dropped for messages, or answered with a short alert
    for callback queries.
    """

    def __init__(self, limits: Optional[Dict[str, tuple[int, int]]] = None):
        self._limits = limits or DEFAULT_LIMITS

    def _infer_key(self, data: Dict[str, Any]) -> str:
        """Determine the rate-limit key from event data."""
        event = data.get("event")
        text = ""

        # Use getattr instead of isinstance so the middleware is testable
        # with mock objects that have .text or .data attributes.
        event_text = getattr(event, "text", None)
        event_data = getattr(event, "data", None)
        if event_text:
            text = event_text.lower()
        elif event_data:
            text = event_data.lower()

        if "login" in text or ":" in text:
            return "login"
        if "/start" in text:
            return "start"
        if "add_to_cart" in text or "remove_from_cart" in text or "корзин" in text:
            return "cart"
        if "checkout" in text or "оформить" in text:
            return "checkout"
        return "default"

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        key = self._infer_key(data)
        max_calls, window = self._limits.get(key, self._limits["default"])

        allowed = await _check_rate_limit(user.id, key, max_calls, window)
        if not allowed:
            logger.warning(
                "Rate limit exceeded: user_id=%s key=%s (%d/%ds)",
                user.id, key, max_calls, window,
            )
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(
                        "⏳ Слишком много запросов. Подождите немного.",
                        show_alert=True,
                    )
                except Exception:
                    pass
            return None  # drop the update

        return await handler(event, data)