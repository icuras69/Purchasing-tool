"""add orderpro purchase order mirror

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orderpro_purchase_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orderpro_id", sa.String(length=100), nullable=False),
        sa.Column("purchase_order_number", sa.String(length=100), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("orderpro_supplier_id", sa.String(length=100), nullable=True),
        sa.Column("supplier_code", sa.String(length=100), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=True),
        sa.Column("order_date", sa.DateTime(), nullable=True),
        sa.Column("expected_date", sa.DateTime(), nullable=True),
        sa.Column("received_date", sa.DateTime(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("orderpro_id"),
    )
    op.create_index(op.f("ix_orderpro_purchase_orders_id"), "orderpro_purchase_orders", ["id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_orders_orderpro_id"), "orderpro_purchase_orders", ["orderpro_id"], unique=True)
    op.create_index(op.f("ix_orderpro_purchase_orders_purchase_order_number"), "orderpro_purchase_orders", ["purchase_order_number"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_orders_supplier_id"), "orderpro_purchase_orders", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_orders_orderpro_supplier_id"), "orderpro_purchase_orders", ["orderpro_supplier_id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_orders_supplier_code"), "orderpro_purchase_orders", ["supplier_code"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_orders_status"), "orderpro_purchase_orders", ["status"], unique=False)

    op.create_table(
        "orderpro_purchase_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orderpro_purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("orderpro_line_id", sa.String(length=100), nullable=True),
        sa.Column("orderpro_line_key", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("orderpro_product_id", sa.String(length=100), nullable=True),
        sa.Column("sku", sa.String(length=255), nullable=True),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("quantity_ordered", sa.Float(), nullable=True),
        sa.Column("quantity_received", sa.Float(), nullable=True),
        sa.Column("quantity_cancelled", sa.Float(), nullable=True),
        sa.Column("quantity_open", sa.Float(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=True),
        sa.Column("expected_date", sa.DateTime(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["orderpro_purchase_order_id"], ["orderpro_purchase_orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("orderpro_purchase_order_id", "orderpro_line_key", name="uq_orderpro_po_lines_order_line_key"),
    )
    op.create_index(op.f("ix_orderpro_purchase_order_lines_id"), "orderpro_purchase_order_lines", ["id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_order_lines_orderpro_purchase_order_id"), "orderpro_purchase_order_lines", ["orderpro_purchase_order_id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_order_lines_orderpro_line_id"), "orderpro_purchase_order_lines", ["orderpro_line_id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_order_lines_product_id"), "orderpro_purchase_order_lines", ["product_id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_order_lines_orderpro_product_id"), "orderpro_purchase_order_lines", ["orderpro_product_id"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_order_lines_sku"), "orderpro_purchase_order_lines", ["sku"], unique=False)
    op.create_index(op.f("ix_orderpro_purchase_order_lines_barcode"), "orderpro_purchase_order_lines", ["barcode"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_orderpro_purchase_order_lines_barcode"), table_name="orderpro_purchase_order_lines")
    op.drop_index(op.f("ix_orderpro_purchase_order_lines_sku"), table_name="orderpro_purchase_order_lines")
    op.drop_index(op.f("ix_orderpro_purchase_order_lines_orderpro_product_id"), table_name="orderpro_purchase_order_lines")
    op.drop_index(op.f("ix_orderpro_purchase_order_lines_product_id"), table_name="orderpro_purchase_order_lines")
    op.drop_index(op.f("ix_orderpro_purchase_order_lines_orderpro_line_id"), table_name="orderpro_purchase_order_lines")
    op.drop_index(op.f("ix_orderpro_purchase_order_lines_orderpro_purchase_order_id"), table_name="orderpro_purchase_order_lines")
    op.drop_index(op.f("ix_orderpro_purchase_order_lines_id"), table_name="orderpro_purchase_order_lines")
    op.drop_table("orderpro_purchase_order_lines")
    op.drop_index(op.f("ix_orderpro_purchase_orders_status"), table_name="orderpro_purchase_orders")
    op.drop_index(op.f("ix_orderpro_purchase_orders_supplier_code"), table_name="orderpro_purchase_orders")
    op.drop_index(op.f("ix_orderpro_purchase_orders_orderpro_supplier_id"), table_name="orderpro_purchase_orders")
    op.drop_index(op.f("ix_orderpro_purchase_orders_supplier_id"), table_name="orderpro_purchase_orders")
    op.drop_index(op.f("ix_orderpro_purchase_orders_purchase_order_number"), table_name="orderpro_purchase_orders")
    op.drop_index(op.f("ix_orderpro_purchase_orders_orderpro_id"), table_name="orderpro_purchase_orders")
    op.drop_index(op.f("ix_orderpro_purchase_orders_id"), table_name="orderpro_purchase_orders")
    op.drop_table("orderpro_purchase_orders")
