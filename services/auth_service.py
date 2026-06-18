"""Authentication service for staff management."""
import logging
from typing import Optional

from database.repositories import UserRepository
from database.models import User

logger = logging.getLogger(__name__)


class AuthService:
    """Handles authentication and staff management logic."""

    def __init__(self, user_repo: UserRepository):
        self._user_repo = user_repo

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user by username and password.
        
        Args:
            username: The username.
            password: The password.
            
        Returns:
            User instance if authentication succeeds, None otherwise.
        """
        user = await self._user_repo.find_by_username(username)
        if user is None:
            logger.warning(f"Authentication failed: user '{username}' not found.")
            return None
        if user.password != password:
            logger.warning(f"Authentication failed: wrong password for '{username}'.")
            return None
        logger.info(f"User '{username}' authenticated successfully as {user.role}.")
        return user

    async def add_waiter(self, username: str, password: str) -> User:
        """Add a new waiter account.
        
        Args:
            username: Unique username.
            password: Waiter password.
            
        Returns:
            The created User instance.
            
        Raises:
            ValueError: If username already exists.
        """
        existing = await self._user_repo.find_by_username(username)
        if existing is not None:
            raise ValueError(f"Username '{username}' already exists.")
        return await self._user_repo.create(username, password, "waiter")

    async def get_all_waiters(self) -> list[User]:
        """Get all waiter accounts.

        Returns:
            List of User instances with role='waiter'.
        """
        return await self._user_repo.get_all_waiters()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: The user ID.

        Returns:
            User instance if found, None otherwise.
        """
        return await self._user_repo.find_by_id(user_id)

    async def delete_waiter(self, user_id: int) -> bool:
        """Delete a waiter account.

        Admin accounts cannot be deleted through this method. Deleting a
        waiter cascades to their assignments, while their historical
        closed-bill records are preserved (waiter_id set to NULL) so that
        revenue totals stay intact.

        Args:
            user_id: The waiter's user ID.

        Returns:
            True if the waiter was found and deleted, False otherwise.

        Raises:
            ValueError: If the account is not a waiter (e.g. an admin) or
                does not exist.
        """
        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise ValueError(f"User with id {user_id} not found.")
        if user.role != "waiter":
            raise ValueError("Администраторов удалять нельзя.")
        deleted = await self._user_repo.delete_by_id(user_id)
        if deleted:
            logger.info(f"Waiter '{user.username}' (id={user_id}) deleted.")
        return deleted

    async def update_chat_id(self, user_id: int, chat_id: int) -> None:
        """Update the Telegram chat_id for a user.
        
        Args:
            user_id: The user ID.
            chat_id: The Telegram chat ID.
        """
        await self._user_repo.update_chat_id(user_id, chat_id)

    async def ensure_admin_exists(self, username: str = "admin", password: str = "password123") -> None:
        """Ensure that a default admin account exists.
        
        Args:
            username: Admin username (default 'admin').
            password: Admin password (default 'password123').
        """
        await self._user_repo.ensure_admin_exists(username, password)