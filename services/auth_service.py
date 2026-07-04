"""Authentication service for staff management."""
import logging
import secrets
from typing import Optional

from database.repositories import UserRepositoryProtocol
from database.models import User
from utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)


class AuthService:
    """Handles authentication and staff management logic."""

    def __init__(self, user_repo: UserRepositoryProtocol):
        self._user_repo = user_repo

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user by username and password.

        The stored value is a bcrypt hash. ``verify_password`` is constant-time
        and returns False if the stored value is not a valid hash (e.g. a
        legacy plain-text password), so login fails for those rows.

        Args:
            username: The username.
            password: The plain-text password.

        Returns:
            User instance if authentication succeeds, None otherwise.
        """
        user = await self._user_repo.find_by_username(username)
        if user is None:
            # Dummy verify to keep response time roughly constant and avoid
            # user-enumeration timing side channels.
            verify_password(password, "$2b$12$" + "x" * 53)
            logger.warning("Authentication failed: user '%s' not found.", username)
            return None
        if not verify_password(password, user.password or ""):
            logger.warning("Authentication failed: wrong password for '%s'.", username)
            return None
        logger.info("User '%s' authenticated successfully as %s.", username, user.role)
        return user

    async def add_waiter(self, username: str, password: str) -> User:
        """Add a new waiter account.

        The password is hashed with bcrypt before storage.

        Raises:
            ValueError: If username already exists or the password is empty.
        """
        if not password:
            raise ValueError("Password must not be empty.")
        existing = await self._user_repo.find_by_username(username)
        if existing is not None:
            raise ValueError(f"Username '{username}' already exists.")
        password_hash = hash_password(password)
        return await self._user_repo.create(username, password_hash, "waiter")

    async def get_all_waiters(self) -> list[User]:
        """Get all waiter accounts."""
        return await self._user_repo.get_all_waiters()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        return await self._user_repo.find_by_id(user_id)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username (public accessor for handlers)."""
        return await self._user_repo.find_by_username(username)

    async def delete_waiter(self, user_id: int) -> bool:
        """Delete a waiter account.

        Admin accounts cannot be deleted through this method.

        Raises:
            ValueError: If the account is not a waiter or does not exist.
        """
        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise ValueError(f"User with id {user_id} not found.")
        if user.role != "waiter":
            raise ValueError("Администраторов удалять нельзя.")
        deleted = await self._user_repo.delete_by_id(user_id)
        if deleted:
            logger.info("Waiter '%s' (id=%s) deleted.", user.username, user_id)
        return deleted

    async def update_chat_id(self, user_id: int, chat_id: int) -> None:
        """Update the Telegram chat_id for a user."""
        await self._user_repo.update_chat_id(user_id, chat_id)

    async def change_password(self, user_id: int, new_password: str) -> None:
        """Set a new password for a user and clear the must-change flag.

        Raises:
            ValueError: If the new password is empty.
        """
        if not new_password:
            raise ValueError("Password must not be empty.")
        password_hash = hash_password(new_password)
        await self._user_repo.update_password(user_id, password_hash, must_change_password=False)
        logger.info("Password changed for user id=%s.", user_id)

    async def ensure_admin_exists(
        self,
        username: str = "admin",
        password: str = "",
    ) -> Optional[str]:
        """Ensure that a default admin account exists, create if not.

        If ``password`` is empty, a random one-time password is generated,
        the admin is created with ``must_change_password=True``, and the
        generated password is returned. Idempotent.

        Returns:
            The generated one-time password if one was created, otherwise None.
        """
        if password:
            password_hash = hash_password(password)
            await self._user_repo.ensure_admin_exists(
                username, password_hash, must_change_password=False
            )
            return None

        one_time = secrets.token_urlsafe(12)
        password_hash = hash_password(one_time)
        created = await self._user_repo.ensure_admin_exists(
            username, password_hash, must_change_password=True
        )
        return one_time if created else None