"""Session storage service for staff authentication.

Provides a unified interface for staff sessions that works with either:

  * **Redis** (production) — sessions survive restarts, are shared across
    instances, have a sliding TTL, and can be explicitly revoked; or
  * **In-memory dict** (development / tests) — when Redis is unavailable.

Each session maps ``telegram_user_id`` -> ``username``. The TTL is refreshed
on every access (sliding expiration) so an active staff member is never
logged out by the TTL alone, while inactive sessions expire automatically.
"""
import logging
from typing import Dict, Optional

from config.settings import settings
from database.redis_connection import get_redis

logger = logging.getLogger(__name__)

_SESSION_PREFIX = "tokio:session:"


class SessionStore:
    """Staff authentication session storage (Redis or in-memory fallback)."""

    def __init__(self) -> None:
        self._memory: Dict[int, str] = {}

    @property
    def is_redis(self) -> bool:
        return bool(settings.redis_url)

    async def get(self, user_id: int) -> Optional[str]:
        redis = await get_redis()
        if redis is not None:
            try:
                key = f"{_SESSION_PREFIX}{user_id}"
                username = await redis.get(key)
                if username is not None:
                    await redis.expire(key, settings.redis_session_ttl)
                return username
            except Exception as exc:
                logger.warning("Redis GET session failed (user_id=%s): %s.", user_id, exc)
                return None
        result = self._memory.get(user_id)
        logger.info("SessionStore.get(user_id=%s) [memory mode] = %r (keys=%s)", user_id, result, list(self._memory.keys()))
        return result

    async def set(self, user_id: int, username: str) -> None:
        redis = await get_redis()
        if redis is not None:
            try:
                await redis.set(
                    f"{_SESSION_PREFIX}{user_id}",
                    username,
                    ex=settings.redis_session_ttl,
                )
                return
            except Exception as exc:
                logger.warning("Redis SET session failed (user_id=%s): %s.", user_id, exc)
        self._memory[user_id] = username
        logger.info("SessionStore.set(user_id=%s, username=%r) [memory mode] (keys=%s)", user_id, username, list(self._memory.keys()))

    async def clear(self, user_id: int) -> None:
        redis = await get_redis()
        if redis is not None:
            try:
                await redis.delete(f"{_SESSION_PREFIX}{user_id}")
            except Exception as exc:
                logger.warning("Redis DELETE session failed (user_id=%s): %s.", user_id, exc)
        self._memory.pop(user_id, None)

    async def revoke_all(self) -> int:
        redis = await get_redis()
        if redis is not None:
            try:
                count = 0
                async for key in redis.scan_iter(match=f"{_SESSION_PREFIX}*", count=100):
                    await redis.delete(key)
                    count += 1
                count += len(self._memory)
                self._memory.clear()
                return count
            except Exception as exc:
                logger.warning("Redis REVOKE ALL failed: %s.", exc)
        count = len(self._memory)
        self._memory.clear()
        return count


_session_store = SessionStore()


def get_session_store() -> SessionStore:
    return _session_store