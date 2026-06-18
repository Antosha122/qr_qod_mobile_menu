"""Cart service for shopping cart operations."""
import logging
from typing import Optional

from database.repositories import CartRepository, MenuRepository
from database.models import Cart, MenuItem

logger = logging.getLogger(__name__)


class CartService:
    """Handles cart-related business logic."""

    def __init__(self, cart_repo: CartRepository, menu_repo: MenuRepository):
        self._cart_repo = cart_repo
        self._menu_repo = menu_repo

    async def get_or_create_cart(self, table_number: int) -> Cart:
        """Get existing cart for a table or create a new one.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            The Cart instance.
        """
        return await self._cart_repo.get_or_create_cart(table_number)

    async def add_item(self, table_number: int, menu_item_id: int, quantity: int) -> None:
        """Add an item to a table's cart.
        
        Args:
            table_number: The restaurant table number.
            menu_item_id: The menu item ID.
            quantity: Quantity to add (must be positive).
            
        Raises:
            ValueError: If quantity is invalid or item not found.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
        
        item = await self._menu_repo.get_item_by_id(menu_item_id)
        if item is None:
            raise ValueError(f"Menu item {menu_item_id} not found.")
        
        cart = await self.get_or_create_cart(table_number)
        await self._cart_repo.add_item(cart.id, menu_item_id, quantity, item.price)
        logger.info(f"Added {quantity} x item {menu_item_id} to table {table_number} cart.")

    async def remove_item(self, table_number: int, menu_item_id: int, quantity: int = 1) -> bool:
        """Remove an item from a table's cart.
        
        Args:
            table_number: The restaurant table number.
            menu_item_id: The menu item ID.
            quantity: Quantity to remove (default 1).
            
        Returns:
            True if item was found and modified, False otherwise.
            
        Raises:
            ValueError: If quantity is invalid.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
        
        cart = await self._cart_repo.get_cart_by_table(table_number)
        if cart is None:
            return False
        return await self._cart_repo.remove_item(cart.id, menu_item_id, quantity)

    async def remove_item_completely(self, table_number: int, menu_item_id: int) -> bool:
        """Completely remove an item from the cart.
        
        Args:
            table_number: The restaurant table number.
            menu_item_id: The menu item ID.
            
        Returns:
            True if item was found and removed, False otherwise.
        """
        cart = await self._cart_repo.get_cart_by_table(table_number)
        if cart is None:
            return False
        return await self._cart_repo.remove_item_completely(cart.id, menu_item_id)

    async def get_items(self, table_number: int) -> list[tuple[MenuItem, int, float]]:
        """Get all items in a table's cart with details.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            List of tuples (MenuItem, quantity, line_total).
        """
        cart = await self._cart_repo.get_cart_by_table(table_number)
        if cart is None:
            return []
        return await self._cart_repo.get_items(cart.id)

    async def get_cart_total(self, table_number: int) -> float:
        """Get the total price of all items in a table's cart.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            Total price as float.
        """
        cart = await self._cart_repo.get_cart_by_table(table_number)
        if cart is None:
            return 0.0
        return await self._cart_repo.get_cart_total(cart.id)

    async def clear_cart(self, table_number: int) -> None:
        """Clear all items from a table's cart.
        
        Args:
            table_number: The restaurant table number.
        """
        await self._cart_repo.clear_cart(table_number)
        logger.info(f"Cleared cart for table {table_number}.")

    async def delete_cart(self, table_number: int) -> None:
        """Delete the cart for a table completely.
        
        Args:
            table_number: The restaurant table number.
        """
        await self._cart_repo.delete_cart(table_number)
        logger.info(f"Deleted cart for table {table_number}.")