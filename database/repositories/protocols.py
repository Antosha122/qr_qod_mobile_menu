"""Protocol (interface) definitions for repositories.

These ``Protocol`` classes describe the public contract each repository
implementation must satisfy. Services are typed against these protocols
rather than concrete classes, so that:

* the concrete repositories (``UserRepository``, ``MenuRepository``, ...)
  can be swapped for fakes/mocks in tests without subclassing;
* the dependency direction is explicit — services depend on *abstractions*,
  not on concrete database implementations.

The protocols are ``@runtime_checkable`` so callers may optionally use
``isinstance`` checks, but structural (duck-typing) compatibility is the
primary mechanism and requires no inheritance.
"""
from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Any, AsyncContextManager, Optional, Protocol, runtime_checkable

from database.models import (
    Cart,
    Category,
    ClosedBill,
    MenuItem,
    Order,
    User,
    WaiterAssignment,
)


# A connection-like object. Kept deliberately loose (``Any``) so the protocols
# do not force a hard dependency on ``asyncpg.Connection`` at type-check time
# (fakes used in tests only implement the small subset of methods they need).
Connection = Any


@runtime_checkable
class UserRepositoryProtocol(Protocol):
    """Public contract for user-related persistence."""

    async def create_table_if_not_exists(self) -> None: ...

    async def find_by_username(self, username: str) -> Optional[User]: ...

    async def create(
        self,
        username: str,
        password: str,
        role: str,
        chat_id: Optional[int] = None,
        must_change_password: bool = False,
    ) -> User: ...

    async def update_chat_id(self, user_id: int, chat_id: int) -> None: ...

    async def update_password(
        self,
        user_id: int,
        password_hash: str,
        must_change_password: bool = False,
    ) -> None: ...

    async def get_all_staff(self) -> list[User]: ...

    async def get_all_waiters(self) -> list[User]: ...

    async def find_by_id(self, user_id: int) -> Optional[User]: ...

    async def delete_by_id(self, user_id: int) -> bool: ...

    async def ensure_admin_exists(
        self,
        username: str,
        password: str,
        must_change_password: bool = False,
    ) -> bool: ...


@runtime_checkable
class MenuRepositoryProtocol(Protocol):
    """Public contract for menu-related persistence."""

    async def get_all_categories(self) -> list[Category]: ...

    async def get_category_by_id(self, category_id: int) -> Optional[Category]: ...

    async def get_items_by_category(self, category_id: int) -> list[MenuItem]: ...

    async def get_item_by_id(self, item_id: int) -> Optional[MenuItem]: ...

    async def create_category(self, name: str) -> Category: ...

    async def create_item(
        self,
        name: str,
        description: Optional[str],
        price: float,
        image_url: Optional[str],
        category_id: int,
    ) -> MenuItem: ...


@runtime_checkable
class CartRepositoryProtocol(Protocol):
    """Public contract for cart-related persistence."""

    async def get_or_create_cart(self, table_number: int) -> Cart: ...

    async def add_item(
        self, cart_id: int, menu_item_id: int, quantity: int, price: float
    ) -> None: ...

    async def remove_item(
        self, cart_id: int, menu_item_id: int, quantity: int = 1
    ) -> bool: ...

    async def remove_item_completely(self, cart_id: int, menu_item_id: int) -> bool: ...

    async def get_items(self, cart_id: int) -> list[tuple[MenuItem, int, float]]: ...

    async def get_cart_total(self, cart_id: int, conn: Optional[Connection] = None) -> float: ...

    async def clear_cart(self, table_number: int, conn: Optional[Connection] = None) -> None: ...

    async def delete_cart(self, table_number: int, conn: Optional[Connection] = None) -> None: ...

    async def get_cart_by_table(
        self, table_number: int, conn: Optional[Connection] = None
    ) -> Optional[Cart]: ...


@runtime_checkable
class OrderRepositoryProtocol(Protocol):
    """Public contract for order-related persistence."""

    async def create(
        self,
        waiter_id: Optional[int],
        table_number: int,
        status: str = "pending",
        conn: Optional[Connection] = None,
    ) -> Order: ...

    async def get_by_id(self, order_id: int) -> Optional[Order]: ...

    async def get_all(self) -> list[Order]: ...

    async def get_by_table(self, table_number: int) -> list[Order]: ...

    async def update_status(self, order_id: int, new_status: str) -> bool: ...

    async def delete(self, order_id: int) -> bool: ...


@runtime_checkable
class WaiterAssignmentRepositoryProtocol(Protocol):
    """Public contract for waiter-table assignment persistence."""

    def acquire_connection(self) -> AsyncContextManager[Connection]:
        """Acquire a raw connection from the underlying pool.

        Returned object is an async context manager yielding a connection
        that can be shared by several repositories inside a single
        transaction (used by :meth:`TableService.close_table`).
        """
        ...

    async def assign_waiter(
        self, waiter_id: int, table_number: int
    ) -> WaiterAssignment: ...

    async def get_by_table(self, table_number: int) -> Optional[WaiterAssignment]: ...

    async def get_open_assignment(
        self, table_number: int
    ) -> Optional[WaiterAssignment]: ...

    async def close_table(
        self, table_number: int, conn: Optional[Connection] = None
    ) -> bool: ...

    async def update_payment_status(
        self, table_number: int, payment_status: str, conn: Optional[Connection] = None
    ) -> bool: ...

    async def is_table_open(self, table_number: int) -> bool: ...

    async def count_open_by_waiter(self, waiter_id: int) -> int: ...

    async def get_all_open(self) -> list[WaiterAssignment]: ...

    async def get_open_by_waiter(self, waiter_id: int) -> list[WaiterAssignment]: ...

    async def unassign_table(self, table_number: int) -> bool: ...


@runtime_checkable
class ClosedBillRepositoryProtocol(Protocol):
    """Public contract for closed-bill (revenue) persistence."""

    async def record_bill(
        self,
        waiter_id: Optional[int],
        table_number: int,
        amount: float,
        conn: Optional[Connection] = None,
    ) -> ClosedBill: ...

    async def get_revenue_since(self, since: datetime) -> tuple[float, int]: ...

    async def get_waiter_revenue_since(
        self, waiter_id: int, since: datetime
    ) -> tuple[float, int]: ...

    async def get_waiter_stats_since(self, since: datetime) -> list[dict]: ...


__all__ = [
    "Connection",
    "UserRepositoryProtocol",
    "MenuRepositoryProtocol",
    "CartRepositoryProtocol",
    "OrderRepositoryProtocol",
    "WaiterAssignmentRepositoryProtocol",
    "ClosedBillRepositoryProtocol",
]