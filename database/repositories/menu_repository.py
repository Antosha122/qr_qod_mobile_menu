"""Repository for menu-related database operations."""
import logging
from typing import Optional

import asyncpg

from database.models import Category, MenuItem

logger = logging.getLogger(__name__)


class MenuRepository:
    """Handles all menu-related database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_all_categories(self) -> list[Category]:
        """Get all menu categories.
        
        Returns:
            List of Category instances.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name FROM categories ORDER BY id"
            )
            return [Category(id=row["id"], name=row["name"]) for row in rows]

    async def get_category_by_id(self, category_id: int) -> Optional[Category]:
        """Get a category by ID.
        
        Args:
            category_id: The category ID.
            
        Returns:
            Category instance if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name FROM categories WHERE id = $1", category_id
            )
            if row is None:
                return None
            return Category(id=row["id"], name=row["name"])

    async def get_items_by_category(self, category_id: int) -> list[MenuItem]:
        """Get all menu items in a category.
        
        Args:
            category_id: The category ID.
            
        Returns:
            List of MenuItem instances.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, description, price, image_url, category_id
                FROM menu
                WHERE category_id = $1
                ORDER BY name
                """,
                category_id,
            )
            return [
                MenuItem(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    price=float(row["price"]),
                    image_url=row["image_url"],
                    category_id=row["category_id"],
                )
                for row in rows
            ]

    async def get_item_by_id(self, item_id: int) -> Optional[MenuItem]:
        """Get a menu item by ID.
        
        Args:
            item_id: The menu item ID.
            
        Returns:
            MenuItem instance if found, None otherwise.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, description, price, image_url, category_id
                FROM menu
                WHERE id = $1
                """,
                item_id,
            )
            if row is None:
                return None
            return MenuItem(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                price=float(row["price"]),
                image_url=row["image_url"],
                category_id=row["category_id"],
            )

    async def create_category(self, name: str) -> Category:
        """Create a new category.
        
        Args:
            name: Category name.
            
        Returns:
            The created Category instance.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO categories (name) VALUES ($1) RETURNING id, name", name
            )
            return Category(id=row["id"], name=row["name"])

    async def create_item(
        self,
        name: str,
        description: Optional[str],
        price: float,
        image_url: Optional[str],
        category_id: int,
    ) -> MenuItem:
        """Create a new menu item.
        
        Args:
            name: Item name.
            description: Item description.
            price: Item price.
            image_url: URL to item image.
            category_id: Category ID.
            
        Returns:
            The created MenuItem instance.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO menu (name, description, price, image_url, category_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, name, description, price, image_url, category_id
                """,
                name, description, price, image_url, category_id,
            )
            return MenuItem(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                price=float(row["price"]),
                image_url=row["image_url"],
                category_id=row["category_id"],
            )