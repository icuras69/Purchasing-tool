"""add product pack rules

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_pack_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("canonical_sku", sa.String(length=255), nullable=True),
        sa.Column("rule_scope", sa.String(length=50), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("order_multiple", sa.Float(), nullable=False),
        sa.Column("pack_type", sa.String(length=50), nullable=True),
        sa.Column("units_per_box", sa.Float(), nullable=True),
        sa.Column("units_per_pallet", sa.Float(), nullable=True),
        sa.Column("pallet_only", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_pack_rules_id"), "product_pack_rules", ["id"], unique=False)
    op.create_index(op.f("ix_product_pack_rules_product_id"), "product_pack_rules", ["product_id"], unique=False)
    op.create_index(op.f("ix_product_pack_rules_supplier_id"), "product_pack_rules", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_product_pack_rules_canonical_sku"), "product_pack_rules", ["canonical_sku"], unique=False)
    op.create_index(op.f("ix_product_pack_rules_is_active"), "product_pack_rules", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_product_pack_rules_is_active"), table_name="product_pack_rules")
    op.drop_index(op.f("ix_product_pack_rules_canonical_sku"), table_name="product_pack_rules")
    op.drop_index(op.f("ix_product_pack_rules_supplier_id"), table_name="product_pack_rules")
    op.drop_index(op.f("ix_product_pack_rules_product_id"), table_name="product_pack_rules")
    op.drop_index(op.f("ix_product_pack_rules_id"), table_name="product_pack_rules")
    op.drop_table("product_pack_rules")
