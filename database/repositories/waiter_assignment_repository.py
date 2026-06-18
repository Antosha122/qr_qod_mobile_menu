"""Repository for waiter assignment database operations."""
import logging
from typing import Optional

import asyncpg

from database.models import WaiterAssignment

logger = logging.getLogger(__name__)


def _row_to_assignment(row) -> WaiterAssignment:
    """Convert an asyncpg Record to a WaiterAssignment instance."""
    return WaiterAssignment(
        id=row["id"],
        waiter_id=row["waiter_id"],
        table_number=row["table_number"],
        status=row["status"],
        assigned_at=row["assigned_at"].isoformat() if row["assigned_at"] else None,
        payment_status=row["payment_status"],
    )


# Columns selected from waiter_assignments, including payment_status.
_SELECT_COLUMNS = (
    "id, waiter_id, table_number, status, payment_status, assigned_at"
)


class WaiterAssignmentRepository:
    """Handles waiter-table assignment database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def assign_waiter(self, waiter_id: int, table_number: int) -> WaiterAssignment:
        """Assign a waiter to a table (or reopen/reset an existing one).

        When reassigning a previously closed table, the assignment is fully
        reset: status becomes 'open' and payment_status becomes 'unpaid'.
        This guarantees a fresh group of guests always starts with a clean
        table, even if the previous guests already paid.

        Args:
            waiter_id: The waiter's user ID.
            table_number: The table number.

        Returns:
            The created/updated WaiterAssignment instance.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO waiter_assignments (waiter_id, table_number, status, payment_status)
                VALUES ($1, $2, 'open', 'unpaid')
                ON CONFLICT (table_number)
                DO UPDATE SET
                    waiter_id = $1,
                    status = 'open',
                    payment_status = 'unpaid',
                    assigned_at = CURRENT_TIMESTAMP
                RETURNING {_SELECT_COLUMNS}
                """,
                waiter_id, table_number,
            )
            return _row_to_assignment(row)

    async def get_by_table(self, table_number: int) -> Optional[WaiterAssignment]:
        """Get assignment for a table.

        Args:
            table_number: The table number.

        Returns:
            WaiterAssignment instance if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM waiter_assignments
                WHERE table_number = $1
                """,
                table_number,
            )
            return _row_to_assignment(row) if row else None

    async def get_open_assignment(self, table_number: int) -> Optional[WaiterAssignment]:
        """Get the open (active) assignment for a table.

        Args:
            table_number: The table number.

        Returns:
            WaiterAssignment instance if open assignment exists, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM waiter_assignments
                WHERE table_number = $1 AND status = 'open'
                """,
                table_number,
            )
            return _row_to_assignment(row) if row else None

    async def close_table(self, table_number: int) -> bool:
        """Close a table assignment and reset its payment status.

        Closing a table releases it for the next guests: the status becomes
        'closed' and the payment_status is reset to 'unpaid' so the table is
        no longer considered "paid". Combined with the cart being cleared by
        the service layer, this makes the table fully fresh for new guests.

        Args:
            table_number: The table number.

        Returns:
            True if assignment was found and closed, False otherwise.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE waiter_assignments "
                "SET status = 'closed', payment_status = 'unpaid' "
                "WHERE table_number = $1",
                table_number,
            )
            return result != "UPDATE 0"

    async def update_payment_status(
        self, table_number: int, payment_status: str
    ) -> bool:
        """Update the payment status of a table assignment.

        Args:
            table_number: The table number.
            payment_status: The new payment status (e.g. 'unpaid', 'requested', 'paid').

        Returns:
            True if assignment was found and updated, False otherwise.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE waiter_assignments SET payment_status = $1 WHERE table_number = $2",
                payment_status, table_number,
            )
            return result != "UPDATE 0"

    async def is_table_open(self, table_number: int) -> bool:
        """Check if a table has an open assignment.

        Args:
            table_number: The table number.

        Returns:
            True if the table has an open assignment, False otherwise.
        """
        assignment = await self.get_open_assignment(table_number)
        return assignment is not None

    async def count_open_by_waiter(self, waiter_id: int) -> int:
        """Count open assignments for a waiter.

        Args:
            waiter_id: The waiter's user ID.

        Returns:
            Number of open assignments for the waiter.
        """
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM waiter_assignments "
                "WHERE waiter_id = $1 AND status = 'open'",
                waiter_id,
            )

    async def get_all_open(self) -> list[WaiterAssignment]:
        """Get all open table assignments.
        
        Returns:
            List of open WaiterAssignment instances.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM waiter_assignments
                WHERE status = 'open'
                ORDER BY assigned_at DESC
                """
            )
            return [_row_to_assignment(row) for row in rows]

    async def get_open_by_waiter(self, waiter_id: int) -> list[WaiterAssignment]:
        """Get all open table assignments for a specific waiter.
        
        Args:
            waiter_id: The waiter's user ID.
            
        Returns:
            List of open WaiterAssignment instances for the waiter.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM waiter_assignments
                WHERE waiter_id = $1 AND status = 'open'
                ORDER BY assigned_at DESC
                """,
                waiter_id,
            )
            return [_row_to_assignment(row) for row in rows]

    async def unassign_table(self, table_number: int) -> bool:
        """Remove the assignment for a table (release it from its waiter).

        Unlike ``close_table`` (which keeps a 'closed' row and is meant for a
        table whose guests have paid and left), this fully *removes* the
        assignment row so the table becomes unassigned. The table's cart is
        left untouched — it will be re-assigned to a waiter automatically the
        next time a guest at that table checks out.

        Use this when an admin wants to take a table off a particular waiter
        without necessarily clearing the order.

        Args:
            table_number: The table number to release.

        Returns:
            True if an assignment row was deleted, False if there was none.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM waiter_assignments WHERE table_number = $1",
                table_number,
            )
            return result != "DELETE 0"
