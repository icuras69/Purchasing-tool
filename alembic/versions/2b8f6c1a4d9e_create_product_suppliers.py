"""create product suppliers

Revision ID: 2b8f6c1a4d9e
Revises: 71e0ed3714ac
Create Date: 2026-05-25 14:05:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b8f6c1a4d9e"
down_revision: Union[str, None] = "71e0ed3714ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("supplier_sku", sa.String(length=255), nullable=True),
        sa.Column("supplier_product_name", sa.String(length=255), nullable=True),
        sa.Column("purchase_price", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("minimum_order_quantity", sa.Float(), nullable=True),
        sa.Column("pack_size", sa.Float(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), nullable=False),
        sa.Column("match_status", sa.String(length=50), nullable=True),
        sa.Column("match_method", sa.String(length=50), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_suppliers_product_id",
        "product_suppliers",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_suppliers_supplier_id",
        "product_suppliers",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_suppliers_id",
        "product_suppliers",
        ["id"],
        unique=False,
    )
    op.create_index(
        "uq_product_suppliers_supplier_sku_not_null",
        "product_suppliers",
        ["supplier_id", "supplier_sku"],
        unique=True,
        postgresql_where=sa.text("supplier_sku IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_suppliers_supplier_sku_not_null", table_name="product_suppliers")
    op.drop_index("ix_product_suppliers_id", table_name="product_suppliers")
    op.drop_index("ix_product_suppliers_supplier_id", table_name="product_suppliers")
    op.drop_index("ix_product_suppliers_product_id", table_name="product_suppliers")
    op.drop_table("product_suppliers")
