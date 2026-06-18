"""Tests for MenuService and OrderService."""
import pytest
from unittest.mock import AsyncMock

from database.models import Category, MenuItem, Order
from services.menu_service import MenuService
from services.order_service import OrderService


class TestMenuService:
    """Tests for the MenuService class."""

    async def test_get_all_categories(self, mock_menu_repo, sample_category):
        """Test getting all categories."""
        mock_menu_repo.get_all_categories.return_value = [sample_category]
        service = MenuService(mock_menu_repo)
        
        result = await service.get_all_categories()
        
        assert len(result) == 1
        assert result[0] == sample_category

    async def test_get_items_by_category(self, mock_menu_repo, sample_menu_item):
        """Test getting items by category."""
        mock_menu_repo.get_items_by_category.return_value = [sample_menu_item]
        service = MenuService(mock_menu_repo)
        
        result = await service.get_items_by_category(1)
        
        assert len(result) == 1
        assert result[0] == sample_menu_item
        mock_menu_repo.get_items_by_category.assert_called_once_with(1)

    async def test_get_item(self, mock_menu_repo, sample_menu_item):
        """Test getting a single item."""
        mock_menu_repo.get_item_by_id.return_value = sample_menu_item
        service = MenuService(mock_menu_repo)
        
        result = await service.get_item(1)
        
        assert result == sample_menu_item

    async def test_get_item_not_found(self, mock_menu_repo):
        """Test getting non-existent item."""
        mock_menu_repo.get_item_by_id.return_value = None
        service = MenuService(mock_menu_repo)
        
        result = await service.get_item(999)
        
        assert result is None

    async def test_create_item_success(self, mock_menu_repo, sample_menu_item):
        """Test creating a menu item successfully."""
        mock_menu_repo.create_item.return_value = sample_menu_item
        service = MenuService(mock_menu_repo)
        
        result = await service.create_item(
            "Ролл", "Описание", 400.0, "http://img.jpg", 1
        )
        
        assert result == sample_menu_item

    async def test_create_item_invalid_price(self, mock_menu_repo):
        """Test creating item with invalid price."""
        service = MenuService(mock_menu_repo)
        
        with pytest.raises(ValueError, match="Price must be positive"):
            await service.create_item("Ролл", "Описание", -100.0, None, 1)

    async def test_create_item_zero_price(self, mock_menu_repo):
        """Test creating item with zero price."""
        service = MenuService(mock_menu_repo)
        
        with pytest.raises(ValueError, match="Price must be positive"):
            await service.create_item("Ролл", "Описание", 0.0, None, 1)


class TestOrderService:
    """Tests for the OrderService class."""

    async def test_create_order(self, mock_order_repo, sample_order):
        """Test creating an order."""
        mock_order_repo.create.return_value = sample_order
        service = OrderService(mock_order_repo, AsyncMock())
        
        result = await service.create_order_from_cart(1, 5, "pending")
        
        assert result == sample_order
        mock_order_repo.create.assert_called_once_with(1, 5, "pending")

    async def test_get_order(self, mock_order_repo, sample_order):
        """Test getting an order by ID."""
        mock_order_repo.get_by_id.return_value = sample_order
        service = OrderService(mock_order_repo, AsyncMock())
        
        result = await service.get_order(1)
        
        assert result == sample_order

    async def test_get_order_not_found(self, mock_order_repo):
        """Test getting non-existent order."""
        mock_order_repo.get_by_id.return_value = None
        service = OrderService(mock_order_repo, AsyncMock())
        
        result = await service.get_order(999)
        
        assert result is None

    async def test_get_all_orders(self, mock_order_repo, sample_order):
        """Test getting all orders."""
        mock_order_repo.get_all.return_value = [sample_order]
        service = OrderService(mock_order_repo, AsyncMock())
        
        result = await service.get_all_orders()
        
        assert len(result) == 1

    async def test_update_order_status(self, mock_order_repo):
        """Test updating order status."""
        mock_order_repo.update_status.return_value = True
        service = OrderService(mock_order_repo, AsyncMock())
        
        result = await service.update_order_status(1, "accepted")
        
        assert result is True
        mock_order_repo.update_status.assert_called_once_with(1, "accepted")

    async def test_delete_order(self, mock_order_repo):
        """Test deleting an order."""
        mock_order_repo.delete.return_value = True
        service = OrderService(mock_order_repo, AsyncMock())
        
        result = await service.delete_order(1)
        
        assert result is True

    async def test_get_orders_by_table(self, mock_order_repo, sample_order):
        """Test getting orders by table."""
        mock_order_repo.get_by_table.return_value = [sample_order]
        service = OrderService(mock_order_repo, AsyncMock())
        
        result = await service.get_orders_by_table(5)
        
        assert len(result) == 1
        mock_order_repo.get_by_table.assert_called_once_with(5)