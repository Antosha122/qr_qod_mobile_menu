"""Common fixtures and mocks for tests."""
import asyncio
import contextlib
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_mock_pool():
    """Create a mock asyncpg pool that supports async context manager.

    The mock pool's ``acquire()`` returns an async context manager that yields
    a mock connection. The connection's ``transaction()`` is also an async
    context manager. This allows services to use ``async with pool.acquire()``
    and ``async with conn.transaction():`` transparently in tests.
    """
    conn = AsyncMock()

    @contextlib.asynccontextmanager
    async def _transaction():
        yield

    conn.transaction = _transaction

    @contextlib.asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = _acquire
    return pool

from database.models import (
    User,
    Category,
    MenuItem,
    Cart,
    CartItem,
    Order,
    WaiterAssignment,
)


@pytest.fixture
def sample_user():
    """Create a sample user for tests."""
    return User(
        id=1,
        username="testadmin",
        password="password123",
        role="admin",
        chat_id=123456789,
    )


@pytest.fixture
def sample_waiter_user():
    """Create a sample waiter user for tests."""
    return User(
        id=2,
        username="testwaiter",
        password="waiterpass",
        role="waiter",
        chat_id=987654321,
    )


@pytest.fixture
def sample_category():
    """Create a sample category for tests."""
    return Category(id=1, name="Горячие роллы")


@pytest.fixture
def sample_menu_item():
    """Create a sample menu item for tests."""
    return MenuItem(
        id=1,
        name="Ролл с тунцом",
        description="Вкусный ролл с тунцом",
        price=400.0,
        image_url="http://example.com/image.jpg",
        category_id=1,
    )


@pytest.fixture
def sample_cart():
    """Create a sample cart for tests."""
    return Cart(id=1, table_number=5, created_at="2024-01-01T12:00:00")


@pytest.fixture
def sample_cart_item():
    """Create a sample cart item for tests."""
    return CartItem(
        id=1,
        cart_id=1,
        menu_item_id=1,
        quantity=2,
        price=400.0,
    )


@pytest.fixture
def sample_order():
    """Create a sample order for tests."""
    return Order(
        id=1,
        waiter_id=1,
        table_number=5,
        status="pending",
        created_at="2024-01-01T12:00:00",
    )


@pytest.fixture
def sample_assignment():
    """Create a sample waiter assignment for tests."""
    return WaiterAssignment(
        id=1,
        waiter_id=2,
        table_number=5,
        status="open",
        assigned_at="2024-01-01T12:00:00",
        payment_status="unpaid",
    )


@pytest.fixture
def mock_user_repo():
    """Create a mock UserRepository."""
    repo = AsyncMock()
    repo.find_by_username = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update_chat_id = AsyncMock()
    repo.get_all_staff = AsyncMock(return_value=[])
    repo.get_all_waiters = AsyncMock(return_value=[])
    repo.ensure_admin_exists = AsyncMock()
    return repo


@pytest.fixture
def mock_menu_repo():
    """Create a mock MenuRepository."""
    repo = AsyncMock()
    repo.get_all_categories = AsyncMock(return_value=[])
    repo.get_category_by_id = AsyncMock(return_value=None)
    repo.get_items_by_category = AsyncMock(return_value=[])
    repo.get_item_by_id = AsyncMock(return_value=None)
    repo.create_category = AsyncMock()
    repo.create_item = AsyncMock()
    return repo


@pytest.fixture
def mock_cart_repo():
    """Create a mock CartRepository."""
    repo = AsyncMock()
    repo.get_or_create_cart = AsyncMock()
    repo.get_cart_by_table = AsyncMock(return_value=None)
    repo.add_item = AsyncMock()
    repo.remove_item = AsyncMock(return_value=True)
    repo.remove_item_completely = AsyncMock(return_value=True)
    repo.get_items = AsyncMock(return_value=[])
    repo.get_cart_total = AsyncMock(return_value=0.0)
    repo.clear_cart = AsyncMock()
    repo.delete_cart = AsyncMock()
    return repo


@pytest.fixture
def mock_order_repo():
    """Create a mock OrderRepository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_all = AsyncMock(return_value=[])
    repo.get_by_table = AsyncMock(return_value=[])
    repo.update_status = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_assignment_repo():
    """Create a mock WaiterAssignmentRepository."""
    repo = AsyncMock()
    repo._pool = _make_mock_pool()
    repo.assign_waiter = AsyncMock()
    repo.get_by_table = AsyncMock(return_value=None)
    repo.get_open_assignment = AsyncMock(return_value=None)
    repo.close_table = AsyncMock(return_value=True)
    repo.update_payment_status = AsyncMock(return_value=True)
    repo.is_table_open = AsyncMock(return_value=False)
    repo.count_open_by_waiter = AsyncMock(return_value=0)
    repo.get_all_open = AsyncMock(return_value=[])
    repo.get_open_by_waiter = AsyncMock(return_value=[])
    return repo
