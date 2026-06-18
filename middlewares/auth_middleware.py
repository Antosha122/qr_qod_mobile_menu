"""Authentication state management for staff bot."""
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from services import AuthService
from database.models import User


# In-memory session storage: {telegram_user_id: username}
# In production, consider using Redis or database-backed sessions.
_sessions: Dict[int, str] = {}


def get_session(user_id: int) -> Optional[str]:
    """Get the username for an authenticated session.
    
    Args:
        user_id: Telegram user ID.
        
    Returns:
        Username if authenticated, None otherwise.
    """
    return _sessions.get(user_id)


def set_session(user_id: int, username: str) -> None:
    """Create or update a session.
    
    Args:
        user_id: Telegram user ID.
        username: The authenticated username.
    """
    _sessions[user_id] = username


def clear_session(user_id: int) -> None:
    """Remove a session.
    
    Args:
        user_id: Telegram user ID.
    """
    _sessions.pop(user_id, None)


def is_authenticated(user_id: int) -> bool:
    """Check if a user is authenticated.
    
    Args:
        user_id: Telegram user ID.
        
    Returns:
        True if authenticated, False otherwise.
    """
    return user_id in _sessions


class StaffAuthMiddleware(BaseMiddleware):
    """Middleware that checks authentication for protected routes.
    
    Attaches `user_authenticated` and `session_username` to handler data.
    Does NOT block unauthenticated users — handlers decide whether to enforce auth.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            username = get_session(user.id)
            data["is_authenticated"] = username is not None
            data["session_username"] = username
        else:
            data["is_authenticated"] = False
            data["session_username"] = None
        
        return await handler(event, data)