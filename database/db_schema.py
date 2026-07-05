"""SQLAlchemy schema definitions — single source of truth for Alembic.

These declarative models describe the *physical* database schema and are used
by Alembic's ``autogenerate`` feature to detect and produce DDL changes.

They are intentionally separated from the lightweight dataclasses in
``database/models.py`` (which act as row-DTOs for the asyncpg-based
repositories). Keeping the schema definition here means DDL lives in one
place and migrations are generated/managed by Alembic rather than being
hand-rolled in application code.

Note: The application's runtime data access still goes through asyncpg
repositories — SQLAlchemy is used here *only* for schema/migration management.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base — carries the ``MetaData`` used by Alembic."""
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'waiter')", name="users_role_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.text("false"),
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class MenuItem(Base):
    __tablename__ = "menu"
    __table_args__ = (
        CheckConstraint("price >= 0", name="menu_price_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # TEXT (widened from VARCHAR(255) by a prior migration).
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False,
    )


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(),
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="cart_items_quantity_check"),
        CheckConstraint("price >= 0", name="cart_items_price_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cart_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False,
    )
    menu_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("menu.id", ondelete="CASCADE"), nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    table_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=func.text("'pending'"),
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(),
    )


class WaiterAssignment(Base):
    __tablename__ = "waiter_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
    )
    table_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=func.text("'open'"),
    )
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=func.text("'unpaid'"),
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(),
    )


class ClosedBill(Base):
    __tablename__ = "closed_bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    table_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=func.text("0"),
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(),
    )


# ---- Indexes (match the previously hand-defined CREATE INDEX statements) ----
Index("idx_menu_category_id", MenuItem.category_id)
Index("idx_cart_items_cart_id", CartItem.cart_id)
Index("idx_cart_items_menu_item_id", CartItem.menu_item_id)
Index("idx_orders_table_number", Order.table_number)
Index("idx_waiter_assignments_table_number", WaiterAssignment.table_number)
Index("idx_waiter_assignments_status", WaiterAssignment.status)
Index("idx_closed_bills_waiter_id", ClosedBill.waiter_id)
Index("idx_closed_bills_closed_at", ClosedBill.closed_at)


__all__ = [
    "Base",
    "User",
    "Category",
    "MenuItem",
    "Cart",
    "CartItem",
    "Order",
    "WaiterAssignment",
    "ClosedBill",
]