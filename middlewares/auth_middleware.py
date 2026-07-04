"""Authentication state management for staff bot.

Sessions are stored via :class:`services.session_store.SessionStore`, which
uses Redis when ``REDIS_URL`` is configured (survives restarts, shared across
instances, sliding TTL, explicit revocation) and falls back to an in-memory
dict otherwise (development / single instance only).

All session access functions are **async coroutines** because Redis
operations are asynchronous.
"""
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.session_store import get_session_store


async def get_session(user_id: int) -> Optional[str]:
    """Get the username for an authenticated session."""
    return await get_session_store().get(user_id)


async def set_session(user_id: int, username: str) -> None:
    """Create or update a session."""
    await get_session_store().set(user_id, username)


async def clear_session(user_id: int) -> None:
    """Remove (revoke) a session."""
    await get_session_store().clear(user_id)


async def is_authenticated(user_id: int) -> bool:
    """Check if a user is authenticated."""
    return await get_session(user_id) is not None


class StaffAuthMiddleware(BaseMiddleware):
    """Middleware that checks authentication for protected routes.

    Attaches ``is_authenticated`` and ``session_username`` to handler data.
    Does NOT block unauthenticated users — handlers decide whether to enforce
    auth.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            username = await get_session(user.id)
            data["is_authenticated"] = username is not None
            data["session_username"] = username
        else:
            data["is_authenticated"] = False
            data["session_username"] = None

        return await handler(event, data)