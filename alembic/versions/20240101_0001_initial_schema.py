"""Initial baseline schema.

Captures the full database schema that previously lived as hand-written DDL
in ``database/models.py`` (``SCHEMA_SQL``) plus the ad-hoc column/type
migrations (``COLUMN_MIGRATIONS`` / ``TYPE_MIGRATIONS``).

This is the first Alembic revision. On a fresh database it creates everything;
on an existing database that was bootstrapped by the legacy ``init_database()``
logic it is a no-op (all statements use ``IF NOT EXISTS``).

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

MIGRATION NOTES
---------------
- ``image_url`` on ``menu`` is created as ``TEXT`` (the final, migrated type —
  earlier versions used ``VARCHAR(255)`` and a separate ``ALTER ... TYPE TEXT``
  migration; both are collapsed into this baseline).
- ``payment_status`` on ``waiter_assignments`` and ``must_change_password`` on
  ``users`` are part of the base schema here (they were previously applied via
  ``COLUMN_MIGRATIONS`` for legacy databases).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect a legacy (pre-Alembic) bootstrap: the schema was created by the
    # old hand-written DDL in ``database/models.py`` so all tables/indexes
    # already exist, but there is no ``alembic_version`` row yet. In that case
    # this baseline migration is a true no-op — Alembic will simply stamp the
    # revision as current. (The docstring above already promises this; this
    # guard makes it actually true instead of failing with DuplicateTableError.)
    bind = op.get_bind()
    schema_already_exists = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'users')"
        )
    ).scalar()
    if schema_already_exists:
        return

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('admin', 'waiter')", name="users_role_check"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    # categories
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # menu
    op.create_table(
        "menu",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        # Final type is TEXT (widened from VARCHAR(255) in a prior ad-hoc migration).
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("price >= 0", name="menu_price_check"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # carts
    op.create_table(
        "carts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("table_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("table_number"),
    )

    # cart_items
    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cart_id", sa.Integer(), nullable=False),
        sa.Column("menu_item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="cart_items_quantity_check"),
        sa.CheckConstraint("price >= 0", name="cart_items_price_check"),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["menu_item_id"], ["menu.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # orders
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("waiter_id", sa.BigInteger(), nullable=True),
        sa.Column("table_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["waiter_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # waiter_assignments
    op.create_table(
        "waiter_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("waiter_id", sa.BigInteger(), nullable=True),
        sa.Column("table_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column(
            "payment_status",
            sa.String(length=20),
            server_default=sa.text("'unpaid'"),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["waiter_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("table_number"),
    )

    # closed_bills
    op.create_table(
        "closed_bills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("waiter_id", sa.BigInteger(), nullable=True),
        sa.Column("table_number", sa.Integer(), nullable=False),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "closed_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["waiter_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes (match the previously hand-defined CREATE INDEX statements)
    op.create_index("idx_menu_category_id", "menu", ["category_id"])
    op.create_index("idx_cart_items_cart_id", "cart_items", ["cart_id"])
    op.create_index("idx_cart_items_menu_item_id", "cart_items", ["menu_item_id"])
    op.create_index("idx_orders_table_number", "orders", ["table_number"])
    op.create_index(
        "idx_waiter_assignments_table_number", "waiter_assignments", ["table_number"],
    )
    op.create_index("idx_waiter_assignments_status", "waiter_assignments", ["status"])
    op.create_index("idx_closed_bills_waiter_id", "closed_bills", ["waiter_id"])
    op.create_index("idx_closed_bills_closed_at", "closed_bills", ["closed_at"])


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_index("idx_closed_bills_closed_at", table_name="closed_bills")
    op.drop_index("idx_closed_bills_waiter_id", table_name="closed_bills")
    op.drop_index("idx_waiter_assignments_status", table_name="waiter_assignments")
    op.drop_index(
        "idx_waiter_assignments_table_number", table_name="waiter_assignments",
    )
    op.drop_index("idx_orders_table_number", table_name="orders")
    op.drop_index("idx_cart_items_menu_item_id", table_name="cart_items")
    op.drop_index("idx_cart_items_cart_id", table_name="cart_items")
    op.drop_index("idx_menu_category_id", table_name="menu")

    op.drop_table("closed_bills")
    op.drop_table("waiter_assignments")
    op.drop_table("orders")
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_table("menu")
    op.drop_table("categories")
    op.drop_table("users")