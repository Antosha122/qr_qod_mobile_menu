"""Repository for cart-related database operations."""
import logging
from typing import Optional

import asyncpg

from database.models import Cart, CartItem, MenuItem

logger = logging.getLogger(__name__)


class CartRepository:
    """Handles all cart-related database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_or_create_cart(self, table_number: int) -> Cart:
        """Get existing cart for a table or create a new one.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            The Cart instance.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, table_number, created_at FROM carts WHERE table_number = $1",
                table_number,
            )
            if row is None:
                row = await conn.fetchrow(
                    """
                    INSERT INTO carts (table_number)
                    VALUES ($1)
                    RETURNING id, table_number, created_at
                    """,
                    table_number,
                )
            return Cart(
                id=row["id"],
                table_number=row["table_number"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
            )

    async def add_item(
        self, cart_id: int, menu_item_id: int, quantity: int, price: float
    ) -> None:
        """Add an item to the cart or increase quantity if it exists.
        
        Args:
            cart_id: The cart ID.
            menu_item_id: The menu item ID.
            quantity: Quantity to add (must be positive).
            price: Unit price.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, quantity FROM cart_items WHERE cart_id = $1 AND menu_item_id = $2",
                cart_id, menu_item_id,
            )
            if existing:
                await conn.execute(
                    "UPDATE cart_items SET quantity = $1 WHERE id = $2",
                    existing["quantity"] + quantity, existing["id"],
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO cart_items (cart_id, menu_item_id, quantity, price)
                    VALUES ($1, $2, $3, $4)
                    """,
                    cart_id, menu_item_id, quantity, price,
                )

    async def remove_item(self, cart_id: int, menu_item_id: int, quantity: int = 1) -> bool:
        """Remove an item from the cart or decrease quantity.
        
        Args:
            cart_id: The cart ID.
            menu_item_id: The menu item ID.
            quantity: Quantity to remove (default 1).
            
        Returns:
            True if item was found and modified, False otherwise.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
            
        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, quantity FROM cart_items WHERE cart_id = $1 AND menu_item_id = $2",
                cart_id, menu_item_id,
            )
            if existing is None:
                return False
                
            new_quantity = existing["quantity"] - quantity
            if new_quantity <= 0:
                await conn.execute("DELETE FROM cart_items WHERE id = $1", existing["id"])
            else:
                await conn.execute(
                    "UPDATE cart_items SET quantity = $1 WHERE id = $2",
                    new_quantity, existing["id"],
                )
            return True

    async def remove_item_completely(self, cart_id: int, menu_item_id: int) -> bool:
        """Completely remove an item from the cart regardless of quantity.
        
        Args:
            cart_id: The cart ID.
            menu_item_id: The menu item ID.
            
        Returns:
            True if item was found and removed, False otherwise.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM cart_items WHERE cart_id = $1 AND menu_item_id = $2",
                cart_id, menu_item_id,
            )
            return result != "DELETE 0"

    async def get_items(self, cart_id: int) -> list[tuple[MenuItem, int, float]]:
        """Get all items in a cart with menu details.
        
        Args:
            cart_id: The cart ID.
            
        Returns:
            List of tuples (MenuItem, quantity, line_total).
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.name, m.description, m.price as unit_price, m.image_url,
                       m.category_id, ci.quantity, ci.price as cart_price
                FROM cart_items ci
                JOIN menu m ON ci.menu_item_id = m.id
                WHERE ci.cart_id = $1
                ORDER BY m.name
                """,
                cart_id,
            )
            return [
                (
                    MenuItem(
                        id=row["id"],
                        name=row["name"],
                        description=row["description"],
                        price=float(row["unit_price"]),
                        image_url=row["image_url"],
                        category_id=row["category_id"],
                    ),
                    row["quantity"],
                    float(row["cart_price"]) * row["quantity"],
                )
                for row in rows
            ]

    async def get_cart_total(self, cart_id: int) -> float:
        """Get the total price of all items in the cart.
        
        Args:
            cart_id: The cart ID.
            
        Returns:
            Total price as float.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(quantity * price), 0) as total
                FROM cart_items
                WHERE cart_id = $1
                """,
                cart_id,
            )
            return float(row["total"]) if row else 0.0

    async def clear_cart(self, table_number: int) -> None:
        """Clear all items from a table's cart.
        
        Args:
            table_number: The restaurant table number.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM cart_items WHERE cart_id = (
                    SELECT id FROM carts WHERE table_number = $1
                )
                """,
                table_number,
            )

    async def delete_cart(self, table_number: int) -> None:
        """Delete the cart for a table completely.
        
        Args:
            table_number: The restaurant table number.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM carts WHERE table_number = $1", table_number
            )

    async def get_cart_by_table(self, table_number: int) -> Optional[Cart]:
        """Get cart for a table without creating if not exists.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            Cart instance if exists, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, table_number, created_at FROM carts WHERE table_number = $1",
                table_number,
            )
            if row is None:
                return None
            return Cart(
                id=row["id"],
                table_number=row["table_number"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
            )