"""Repository for order-related database operations."""
import logging
from typing import Optional

import asyncpg

from database.models import Order

logger = logging.getLogger(__name__)


class OrderRepository:
    """Handles all order-related database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create(self, waiter_id: Optional[int], table_number: int, status: str = "pending", conn=None) -> Order:
        """Create a new order.

        Args:
            waiter_id: ID of the waiter handling the order (optional).
            table_number: The restaurant table number.
            status: Order status (default 'pending').
            conn: Optional existing connection (for transactions).

        Returns:
            The created Order instance.
        """
        sql = """
            INSERT INTO orders (waiter_id, table_number, status)
            VALUES ($1, $2, $3)
            RETURNING id, waiter_id, table_number, status, created_at
        """
        if conn is not None:
            row = await conn.fetchrow(sql, waiter_id, table_number, status)
        else:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, waiter_id, table_number, status)
        return Order(
            id=row["id"],
            waiter_id=row["waiter_id"],
            table_number=row["table_number"],
            status=row["status"],
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
        )

    async def get_by_id(self, order_id: int) -> Optional[Order]:
        """Get an order by ID.
        
        Args:
            order_id: The order ID.
            
        Returns:
            Order instance if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, waiter_id, table_number, status, created_at
                FROM orders
                WHERE id = $1
                """,
                order_id,
            )
            if row is None:
                return None
            return Order(
                id=row["id"],
                waiter_id=row["waiter_id"],
                table_number=row["table_number"],
                status=row["status"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
            )

    async def get_all(self) -> list[Order]:
        """Get all orders.
        
        Returns:
            List of all Order instances, ordered by creation date (newest first).
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, waiter_id, table_number, status, created_at
                FROM orders
                ORDER BY created_at DESC
                """
            )
            return [
                Order(
                    id=row["id"],
                    waiter_id=row["waiter_id"],
                    table_number=row["table_number"],
                    status=row["status"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else None,
                )
                for row in rows
            ]

    async def get_by_table(self, table_number: int) -> list[Order]:
        """Get all orders for a specific table.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            List of Order instances for the table.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, waiter_id, table_number, status, created_at
                FROM orders
                WHERE table_number = $1
                ORDER BY created_at DESC
                """,
                table_number,
            )
            return [
                Order(
                    id=row["id"],
                    waiter_id=row["waiter_id"],
                    table_number=row["table_number"],
                    status=row["status"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else None,
                )
                for row in rows
            ]

    async def update_status(self, order_id: int, new_status: str) -> bool:
        """Update the status of an order.
        
        Args:
            order_id: The order ID.
            new_status: The new status value.
            
        Returns:
            True if the order was found and updated, False otherwise.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE orders SET status = $1 WHERE id = $2",
                new_status, order_id,
            )
            return result != "UPDATE 0"

    async def delete(self, order_id: int) -> bool:
        """Delete an order by ID.
        
        Args:
            order_id: The order ID.
            
        Returns:
            True if the order was found and deleted, False otherwise.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM orders WHERE id = $1", order_id)
            return result != "DELETE 0"