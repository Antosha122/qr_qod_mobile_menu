"""Order service for order management."""
import logging
from typing import Optional

from database.repositories import OrderRepository, CartRepository
from database.models import Order

logger = logging.getLogger(__name__)


class OrderService:
    """Handles order-related business logic."""

    def __init__(self, order_repo: OrderRepository, cart_repo: CartRepository):
        self._order_repo = order_repo
        self._cart_repo = cart_repo

    async def create_order_from_cart(
        self, waiter_id: Optional[int], table_number: int, status: str = "pending"
    ) -> Order:
        """Create an order from a table's cart contents.
        
        Args:
            waiter_id: ID of the waiter (optional).
            table_number: The restaurant table number.
            status: Order status (default 'pending').
            
        Returns:
            The created Order instance.
        """
        order = await self._order_repo.create(waiter_id, table_number, status)
        logger.info(f"Created order {order.id} for table {table_number}.")
        return order

    async def get_order(self, order_id: int) -> Optional[Order]:
        """Get an order by ID.
        
        Args:
            order_id: The order ID.
            
        Returns:
            Order instance if found, None otherwise.
        """
        return await self._order_repo.get_by_id(order_id)

    async def get_all_orders(self) -> list[Order]:
        """Get all orders.
        
        Returns:
            List of all Order instances.
        """
        return await self._order_repo.get_all()

    async def get_orders_by_table(self, table_number: int) -> list[Order]:
        """Get all orders for a specific table.
        
        Args:
            table_number: The restaurant table number.
            
        Returns:
            List of Order instances for the table.
        """
        return await self._order_repo.get_by_table(table_number)

    async def update_order_status(self, order_id: int, new_status: str) -> bool:
        """Update the status of an order.
        
        Args:
            order_id: The order ID.
            new_status: The new status value.
            
        Returns:
            True if the order was found and updated, False otherwise.
        """
        result = await self._order_repo.update_status(order_id, new_status)
        if result:
            logger.info(f"Order {order_id} status updated to '{new_status}'.")
        return result

    async def delete_order(self, order_id: int) -> bool:
        """Delete an order by ID.
        
        Args:
            order_id: The order ID.
            
        Returns:
            True if the order was found and deleted, False otherwise.
        """
        result = await self._order_repo.delete(order_id)
        if result:
            logger.info(f"Order {order_id} deleted.")
        return result