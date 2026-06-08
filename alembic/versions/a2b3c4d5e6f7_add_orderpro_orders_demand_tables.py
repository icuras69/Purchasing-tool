"""add orderpro orders demand tables

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-01 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orderpro_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orderpro_id", sa.String(length=100), nullable=False),
        sa.Column("order_number", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("order_date", sa.DateTime(), nullable=True),
        sa.Column("required_date", sa.DateTime(), nullable=True),
        sa.Column("shipped_date", sa.DateTime(), nullable=True),
        sa.Column("orderpro_warehouse_id", sa.String(length=100), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("subtotal", sa.Float(), nullable=True),
        sa.Column("tax_amount", sa.Float(), nullable=True),
        sa.Column("shipping_cost", sa.Float(), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("raw_snapshot", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("orderpro_id", name="uq_orderpro_orders_orderpro_id"),
    )
    op.create_index("ix_orderpro_orders_id", "orderpro_orders", ["id"], unique=False)
    op.create_index("ix_orderpro_orders_orderpro_id", "orderpro_orders", ["orderpro_id"], unique=True)
    op.create_index("ix_orderpro_orders_order_number", "orderpro_orders", ["order_number"], unique=False)
    op.create_index("ix_orderpro_orders_status", "orderpro_orders", ["status"], unique=False)
    op.create_index("ix_orderpro_orders_order_date", "orderpro_orders", ["order_date"], unique=False)
    op.create_index("ix_orderpro_orders_orderpro_warehouse_id", "orderpro_orders", ["orderpro_warehouse_id"], unique=False)

    op.create_table(
        "orderpro_order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orderpro_id", sa.String(length=100), nullable=True),
        sa.Column("orderpro_line_key", sa.String(length=255), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("orderpro_product_id", sa.String(length=100), nullable=True),
        sa.Column("sku", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Float(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.Column("raw_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["order_id"], ["orderpro_orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "orderpro_line_key", name="uq_orderpro_order_items_order_line_key"),
    )
    op.create_index("ix_orderpro_order_items_id", "orderpro_order_items", ["id"], unique=False)
    op.create_index("ix_orderpro_order_items_orderpro_id", "orderpro_order_items", ["orderpro_id"], unique=False)
    op.create_index("ix_orderpro_order_items_order_id", "orderpro_order_items", ["order_id"], unique=False)
    op.create_index("ix_orderpro_order_items_product_id", "orderpro_order_items", ["product_id"], unique=False)
    op.create_index(
        "ix_orderpro_order_items_orderpro_product_id",
        "orderpro_order_items",
        ["orderpro_product_id"],
        unique=False,
    )
    op.create_index("ix_orderpro_order_items_sku", "orderpro_order_items", ["sku"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_orderpro_order_items_sku", table_name="orderpro_order_items")
    op.drop_index("ix_orderpro_order_items_orderpro_product_id", table_name="orderpro_order_items")
    op.drop_index("ix_orderpro_order_items_product_id", table_name="orderpro_order_items")
    op.drop_index("ix_orderpro_order_items_order_id", table_name="orderpro_order_items")
    op.drop_index("ix_orderpro_order_items_orderpro_id", table_name="orderpro_order_items")
    op.drop_index("ix_orderpro_order_items_id", table_name="orderpro_order_items")
    op.drop_table("orderpro_order_items")

    op.drop_index("ix_orderpro_orders_orderpro_warehouse_id", table_name="orderpro_orders")
    op.drop_index("ix_orderpro_orders_order_date", table_name="orderpro_orders")
    op.drop_index("ix_orderpro_orders_status", table_name="orderpro_orders")
    op.drop_index("ix_orderpro_orders_order_number", table_name="orderpro_orders")
    op.drop_index("ix_orderpro_orders_orderpro_id", table_name="orderpro_orders")
    op.drop_index("ix_orderpro_orders_id", table_name="orderpro_orders")
    op.drop_table("orderpro_orders")
