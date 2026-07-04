"""Repository for user-related database operations.

All SELECT queries include ``must_change_password`` so that callers always
receive a fully-populated :class:`~database.models.User` dataclass.
"""
import logging
from typing import Optional

import asyncpg

from database.models import User

logger = logging.getLogger(__name__)

# Reusable column list — keep in sync with the User dataclass fields order.
_USER_COLUMNS = "id, username, password, role, chat_id, must_change_password"


class UserRepository:
    """Handles all user-related database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create_table_if_not_exists(self) -> None:
        """Ensure the users table exists (includes must_change_password)."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255),
                    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'waiter')),
                    chat_id BIGINT,
                    must_change_password BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)

    async def find_by_username(self, username: str) -> Optional[User]:
        """Find a user by username.

        Args:
            username: The username to search for.

        Returns:
            User instance if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_USER_COLUMNS} FROM users WHERE username = $1",
                username,
            )
            if row is None:
                return None
            return self._row_to_user(row)

    async def create(
        self,
        username: str,
        password: str,
        role: str,
        chat_id: Optional[int] = None,
        must_change_password: bool = False,
    ) -> User:
        """Create a new user.

        Args:
            username: Unique username.
            password: User password (already hashed by the service layer).
            role: User role ('admin' or 'waiter').
            chat_id: Optional Telegram chat ID.
            must_change_password: Forces a password change on next login.

        Returns:
            The created User instance.

        Raises:
            asyncpg.UniqueViolationError: If username already exists.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO users (username, password, role, chat_id, must_change_password)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING {_USER_COLUMNS}
                """,
                username, password, role, chat_id, must_change_password,
            )
            return self._row_to_user(row)

    async def update_chat_id(self, user_id: int, chat_id: int) -> None:
        """Update chat_id for a user.

        Args:
            user_id: The user's ID.
            chat_id: The Telegram chat ID to set.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET chat_id = $1 WHERE id = $2",
                chat_id, user_id,
            )

    async def update_password(
        self,
        user_id: int,
        password_hash: str,
        must_change_password: bool = False,
    ) -> None:
        """Update a user's password hash and the must-change flag.

        Args:
            user_id: The user's ID.
            password_hash: The new bcrypt hash to store.
            must_change_password: Whether the user must change this password on
                next login. Pass False after the user sets their own password.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET password = $1, must_change_password = $2 "
                "WHERE id = $3",
                password_hash, must_change_password, user_id,
            )

    async def get_all_staff(self) -> list[User]:
        """Get all staff users (admins and waiters).

        Returns:
            List of all User instances.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_USER_COLUMNS} FROM users ORDER BY id"
            )
            return [self._row_to_user(row) for row in rows]

    async def get_all_waiters(self) -> list[User]:
        """Get all users with the 'waiter' role.

        Returns:
            List of User instances with role='waiter', ordered by id.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_USER_COLUMNS} FROM users "
                "WHERE role = 'waiter' ORDER BY id"
            )
            return [self._row_to_user(row) for row in rows]

    async def find_by_id(self, user_id: int) -> Optional[User]:
        """Find a user by ID.

        Args:
            user_id: The user ID to search for.

        Returns:
            User instance if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_USER_COLUMNS} FROM users WHERE id = $1",
                user_id,
            )
            if row is None:
                return None
            return self._row_to_user(row)

    async def delete_by_id(self, user_id: int) -> bool:
        """Delete a user by ID.

        Deleting a waiter cascades to their ``waiter_assignments`` (ON DELETE
        CASCADE), and their historical ``closed_bills`` rows keep their data
        with ``waiter_id`` set to NULL (ON DELETE SET NULL) so revenue totals
        are preserved for reporting.

        Args:
            user_id: The user ID to delete.

        Returns:
            True if the user was found and deleted, False otherwise.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM users WHERE id = $1", user_id
            )
            return result != "DELETE 0"

    async def ensure_admin_exists(
        self,
        username: str,
        password: str,
        must_change_password: bool = False,
    ) -> bool:
        """Ensure that an admin account exists; create it if not.

        Idempotent: if the admin already exists nothing is changed.

        Args:
            username: Admin username.
            password: Admin password hash (already hashed by the service layer).
            must_change_password: Force a password change on first login.

        Returns:
            True if a new admin was created, False if it already existed.
        """
        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM users WHERE username = $1", username
            )
            if existing is None:
                await conn.execute(
                    """
                    INSERT INTO users (username, password, role, must_change_password)
                    VALUES ($1, $2, 'admin', $3)
                    """,
                    username, password, must_change_password,
                )
                logger.info(f"Default admin account '{username}' created.")
                return True
            return False

    @staticmethod
    def _row_to_user(row: asyncpg.Record) -> User:
        """Convert an asyncpg Record into a User dataclass."""
        return User(
            id=row["id"],
            username=row["username"],
            password=row["password"],
            role=row["role"],
            chat_id=row["chat_id"],
            must_change_password=row["must_change_password"],
        )