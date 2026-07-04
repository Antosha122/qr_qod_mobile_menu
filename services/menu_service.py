"""Menu service for category and item management."""
import logging
from typing import Optional

from database.repositories import MenuRepositoryProtocol
from database.models import Category, MenuItem

logger = logging.getLogger(__name__)


class MenuService:
    """Handles menu-related business logic."""

    def __init__(self, menu_repo: MenuRepositoryProtocol):
        self._menu_repo = menu_repo

    async def get_all_categories(self) -> list[Category]:
        """Get all menu categories.
        
        Returns:
            List of Category instances.
        """
        return await self._menu_repo.get_all_categories()

    async def get_items_by_category(self, category_id: int) -> list[MenuItem]:
        """Get all items in a category.
        
        Args:
            category_id: The category ID.
            
        Returns:
            List of MenuItem instances.
        """
        return await self._menu_repo.get_items_by_category(category_id)

    async def get_item(self, item_id: int) -> Optional[MenuItem]:
        """Get a single menu item by ID.
        
        Args:
            item_id: The menu item ID.
            
        Returns:
            MenuItem instance if found, None otherwise.
        """
        return await self._menu_repo.get_item_by_id(item_id)

    async def create_category(self, name: str) -> Category:
        """Create a new category.
        
        Args:
            name: Category name.
            
        Returns:
            The created Category instance.
        """
        return await self._menu_repo.create_category(name)

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
            price: Item price (must be positive).
            image_url: URL to item image.
            category_id: Category ID.
            
        Returns:
            The created MenuItem instance.
            
        Raises:
            ValueError: If price is not positive.
        """
        if price <= 0:
            raise ValueError("Price must be positive.")
        return await self._menu_repo.create_item(name, description, price, image_url, category_id)