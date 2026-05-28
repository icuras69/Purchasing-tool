"""add purchase order workflow

Revision ID: 9c1d4e8f2a34
Revises: 2b8f6c1a4d9e
Create Date: 2026-05-28 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c1d4e8f2a34"
down_revision: Union[str, None] = "2b8f6c1a4d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("supplier_id", sa.Integer(), nullable=True))
    op.add_column("purchase_orders", sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"))
    op.add_column("purchase_orders", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("purchase_orders", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("purchase_orders", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("purchase_orders", sa.Column("issued_at", sa.DateTime(), nullable=True))
    op.add_column("purchase_orders", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("purchase_orders", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("purchase_orders", sa.Column("total_amount", sa.Float(), nullable=True))
    op.add_column("purchase_orders", sa.Column("currency", sa.String(length=10), nullable=True))
    op.add_column("purchase_orders", sa.Column("created_by", sa.String(length=255), nullable=True))
    op.add_column("purchase_orders", sa.Column("approved_by", sa.String(length=255), nullable=True))
    op.create_foreign_key(
        "fk_purchase_orders_supplier_id_suppliers",
        "purchase_orders",
        "suppliers",
        ["supplier_id"],
        ["id"],
    )
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"], unique=False)
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"], unique=False)

    op.alter_column("purchase_orders", "product_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("purchase_orders", "order_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("purchase_orders", "qty_ordered", existing_type=sa.Float(), nullable=True)
    op.alter_column("purchase_orders", "unit_cost", existing_type=sa.Float(), nullable=True)

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_supplier_id", sa.Integer(), nullable=False),
        sa.Column("supplier_sku", sa.String(length=255), nullable=True),
        sa.Column("supplier_product_name", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("line_total", sa.Float(), nullable=True),
        sa.Column("minimum_order_quantity", sa.Float(), nullable=True),
        sa.Column("pack_size", sa.Float(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["product_supplier_id"], ["product_suppliers.id"]),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_order_lines_id", "purchase_order_lines", ["id"], unique=False)
    op.create_index("ix_purchase_order_lines_product_id", "purchase_order_lines", ["product_id"], unique=False)
    op.create_index(
        "ix_purchase_order_lines_product_supplier_id",
        "purchase_order_lines",
        ["product_supplier_id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_order_lines_purchase_order_id",
        "purchase_order_lines",
        ["purchase_order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_order_lines_purchase_order_id", table_name="purchase_order_lines")
    op.drop_index("ix_purchase_order_lines_product_supplier_id", table_name="purchase_order_lines")
    op.drop_index("ix_purchase_order_lines_product_id", table_name="purchase_order_lines")
    op.drop_index("ix_purchase_order_lines_id", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")

    op.alter_column("purchase_orders", "unit_cost", existing_type=sa.Float(), nullable=False)
    op.alter_column("purchase_orders", "qty_ordered", existing_type=sa.Float(), nullable=False)
    op.alter_column("purchase_orders", "order_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("purchase_orders", "product_id", existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
    op.drop_constraint("fk_purchase_orders_supplier_id_suppliers", "purchase_orders", type_="foreignkey")
    op.drop_column("purchase_orders", "approved_by")
    op.drop_column("purchase_orders", "created_by")
    op.drop_column("purchase_orders", "currency")
    op.drop_column("purchase_orders", "total_amount")
    op.drop_column("purchase_orders", "notes")
    op.drop_column("purchase_orders", "cancelled_at")
    op.drop_column("purchase_orders", "issued_at")
    op.drop_column("purchase_orders", "approved_at")
    op.drop_column("purchase_orders", "updated_at")
    op.drop_column("purchase_orders", "created_at")
    op.drop_column("purchase_orders", "status")
    op.drop_column("purchase_orders", "supplier_id")
