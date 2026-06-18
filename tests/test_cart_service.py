"""Tests for CartService."""
import pytest
from unittest.mock import AsyncMock

from database.models import Cart, MenuItem
from services.cart_service import CartService


class TestCartService:
    """Tests for the CartService class."""

    async def test_get_or_create_cart(self, mock_cart_repo, sample_cart):
        """Test getting or creating a cart."""
        mock_cart_repo.get_or_create_cart.return_value = sample_cart
        service = CartService(mock_cart_repo, AsyncMock())
        
        result = await service.get_or_create_cart(5)
        
        assert result == sample_cart
        mock_cart_repo.get_or_create_cart.assert_called_once_with(5)

    async def test_add_item_success(
        self, mock_cart_repo, mock_menu_repo, sample_menu_item, sample_cart
    ):
        """Test adding an item to cart successfully."""
        mock_menu_repo.get_item_by_id.return_value = sample_menu_item
        mock_cart_repo.get_or_create_cart.return_value = sample_cart
        service = CartService(mock_cart_repo, mock_menu_repo)
        
        await service.add_item(5, 1, 2)
        
        mock_cart_repo.add_item.assert_called_once_with(1, 1, 2, 400.0)

    async def test_add_item_invalid_quantity(
        self, mock_cart_repo, mock_menu_repo
    ):
        """Test adding item with invalid quantity."""
        service = CartService(mock_cart_repo, mock_menu_repo)
        
        with pytest.raises(ValueError, match="Quantity must be positive"):
            await service.add_item(5, 1, 0)

    async def test_add_item_not_found(self, mock_cart_repo, mock_menu_repo):
        """Test adding non-existent item."""
        mock_menu_repo.get_item_by_id.return_value = None
        service = CartService(mock_cart_repo, mock_menu_repo)
        
        with pytest.raises(ValueError, match="not found"):
            await service.add_item(5, 999, 1)

    async def test_remove_item_success(self, mock_cart_repo, sample_cart):
        """Test removing an item from cart."""
        mock_cart_repo.get_cart_by_table.return_value = sample_cart
        mock_cart_repo.remove_item.return_value = True
        service = CartService(mock_cart_repo, AsyncMock())
        
        result = await service.remove_item(5, 1, 1)
        
        assert result is True
        mock_cart_repo.remove_item.assert_called_once_with(1, 1, 1)

    async def test_remove_item_no_cart(self, mock_cart_repo):
        """Test removing item when no cart exists."""
        mock_cart_repo.get_cart_by_table.return_value = None
        service = CartService(mock_cart_repo, AsyncMock())
        
        result = await service.remove_item(5, 1, 1)
        
        assert result is False

    async def test_remove_item_invalid_quantity(self, mock_cart_repo):
        """Test removing item with invalid quantity."""
        service = CartService(mock_cart_repo, AsyncMock())
        
        with pytest.raises(ValueError, match="Quantity must be positive"):
            await service.remove_item(5, 1, 0)

    async def test_get_items_empty(self, mock_cart_repo):
        """Test getting items from non-existent cart."""
        mock_cart_repo.get_cart_by_table.return_value = None
        service = CartService(mock_cart_repo, AsyncMock())
        
        result = await service.get_items(5)
        
        assert result == []

    async def test_get_cart_total_no_cart(self, mock_cart_repo):
        """Test getting total for non-existent cart."""
        mock_cart_repo.get_cart_by_table.return_value = None
        service = CartService(mock_cart_repo, AsyncMock())
        
        result = await service.get_cart_total(5)
        
        assert result == 0.0

    async def test_clear_cart(self, mock_cart_repo):
        """Test clearing a cart."""
        service = CartService(mock_cart_repo, AsyncMock())
        
        await service.clear_cart(5)
        
        mock_cart_repo.clear_cart.assert_called_once_with(5)

    async def test_delete_cart(self, mock_cart_repo):
        """Test deleting a cart."""
        service = CartService(mock_cart_repo, AsyncMock())
        
        await service.delete_cart(5)
        
        mock_cart_repo.delete_cart.assert_called_once_with(5)