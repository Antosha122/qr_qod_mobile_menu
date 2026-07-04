"""Repository for closed-bill (historical revenue) database operations.

When staff closes a table, the table's cart is cleared. To keep revenue and
per-waiter statistics queryable after that, a snapshot of the closed bill
(amount, waiter, table, timestamp) is stored in the ``closed_bills`` table.
"""
import logging
from datetime import datetime
from typing import Optional

import asyncpg

from database.models import ClosedBill

logger = logging.getLogger(__name__)


def _row_to_bill(row) -> ClosedBill:
    """Convert an asyncpg Record to a ClosedBill instance."""
    return ClosedBill(
        id=row["id"],
        waiter_id=row["waiter_id"],
        table_number=row["table_number"],
        amount=float(row["amount"]),
        closed_at=row["closed_at"].isoformat() if row["closed_at"] else None,
    )


_SELECT_COLUMNS = "id, waiter_id, table_number, amount, closed_at"


class ClosedBillRepository:
    """Handles closed-bill database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def record_bill(
        self,
        waiter_id: Optional[int],
        table_number: int,
        amount: float,
        conn=None,
    ) -> ClosedBill:
        """Record a closed bill (a finalized table payment).

        Args:
            waiter_id: The waiter who served the table (None if unknown).
            table_number: The table that was closed.
            amount: The total amount paid for the table.

        Returns:
            The created ClosedBill instance.
        """
        sql = f"""
            INSERT INTO closed_bills (waiter_id, table_number, amount)
            VALUES ($1, $2, $3)
            RETURNING {_SELECT_COLUMNS}
        """
        if conn is not None:
            row = await conn.fetchrow(sql, waiter_id, table_number, amount)
        else:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, waiter_id, table_number, amount)
        logger.info(
            f"Recorded closed bill: table {table_number}, "
            f"waiter {waiter_id}, amount {amount}."
        )
        return _row_to_bill(row)

    async def get_revenue_since(self, since: datetime) -> tuple[float, int]:
        """Get total revenue and bill count since a given timestamp.

        Args:
            since: The start timestamp (inclusive).

        Returns:
            A tuple of (total_amount, bill_count).
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt
                FROM closed_bills
                WHERE closed_at >= $1
                """,
                since,
            )
            if row is None:
                return 0.0, 0
            return float(row["total"]), int(row["cnt"])

    async def get_waiter_revenue_since(
        self, waiter_id: int, since: datetime
    ) -> tuple[float, int]:
        """Get total revenue and bill count for a waiter since a timestamp.

        Args:
            waiter_id: The waiter's user ID.
            since: The start timestamp (inclusive).

        Returns:
            A tuple of (total_amount, bill_count).
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt
                FROM closed_bills
                WHERE waiter_id = $1 AND closed_at >= $2
                """,
                waiter_id, since,
            )
            if row is None:
                return 0.0, 0
            return float(row["total"]), int(row["cnt"])

    async def get_waiter_stats_since(
        self, since: datetime
    ) -> list[dict]:
        """Get per-waiter revenue and closed-table counts since a timestamp.

        Args:
            since: The start timestamp (inclusive).

        Returns:
            A list of dicts with keys: ``waiter_id``, ``waiter_username``,
            ``tables_closed``, ``total_amount``. Ordered by total_amount DESC.
            Waiters with no closed bills in the period are still included
            (with zeroes) so the admin sees the full staff roster.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.id AS waiter_id,
                       u.username AS waiter_username,
                       COALESCE(cb.tables_closed, 0) AS tables_closed,
                       COALESCE(cb.total_amount, 0) AS total_amount
                FROM users u
                LEFT JOIN (
                    SELECT waiter_id,
                           COUNT(*) AS tables_closed,
                           SUM(amount) AS total_amount
                    FROM closed_bills
                    WHERE closed_at >= $1
                    GROUP BY waiter_id
                ) cb ON cb.waiter_id = u.id
                WHERE u.role = 'waiter'
                ORDER BY total_amount DESC, u.id ASC
                """,
                since,
            )
            return [
                {
                    "waiter_id": row["waiter_id"],
                    "waiter_username": row["waiter_username"],
                    "tables_closed": int(row["tables_closed"]),
                    "total_amount": float(row["total_amount"]),
                }
                for row in rows
            ]