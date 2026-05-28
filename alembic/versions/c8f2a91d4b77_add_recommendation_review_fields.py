"""add recommendation review fields

Revision ID: c8f2a91d4b77
Revises: b7a4c2d9e101
Create Date: 2026-05-28 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f2a91d4b77"
down_revision: Union[str, None] = "b7a4c2d9e101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("supplier_id", sa.Integer(), nullable=True))
    op.add_column("recommendations", sa.Column("product_supplier_id", sa.Integer(), nullable=True))
    op.add_column("recommendations", sa.Column("converted_purchase_order_id", sa.Integer(), nullable=True))
    op.add_column("recommendations", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("recommendations", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("recommendations", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "recommendations",
        sa.Column("recommendation_type", sa.String(length=50), nullable=False, server_default="reorder"),
    )
    op.add_column(
        "recommendations",
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending_review"),
    )
    op.add_column("recommendations", sa.Column("recommended_supplier_name", sa.String(length=255), nullable=True))
    op.add_column("recommendations", sa.Column("recommended_supplier_sku", sa.String(length=255), nullable=True))
    op.add_column("recommendations", sa.Column("estimated_unit_cost", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("estimated_total_cost", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("currency", sa.String(length=10), nullable=True))
    op.add_column("recommendations", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("recommendations", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("input_snapshot", sa.JSON(), nullable=True))
    op.add_column("recommendations", sa.Column("forecast_snapshot", sa.JSON(), nullable=True))
    op.add_column("recommendations", sa.Column("supplier_context_snapshot", sa.JSON(), nullable=True))
    op.add_column("recommendations", sa.Column("model_name", sa.String(length=255), nullable=True))
    op.add_column("recommendations", sa.Column("prompt_version", sa.String(length=255), nullable=True))
    op.add_column(
        "recommendations",
        sa.Column("generated_by", sa.String(length=50), nullable=False, server_default="system"),
    )
    op.add_column("recommendations", sa.Column("reviewed_by", sa.String(length=255), nullable=True))
    op.add_column("recommendations", sa.Column("rejected_reason", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_recommendations_supplier_id_suppliers",
        "recommendations",
        "suppliers",
        ["supplier_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_recommendations_product_supplier_id_product_suppliers",
        "recommendations",
        "product_suppliers",
        ["product_supplier_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_recommendations_converted_purchase_order_id_purchase_orders",
        "recommendations",
        "purchase_orders",
        ["converted_purchase_order_id"],
        ["id"],
    )
    op.create_index("ix_recommendations_supplier_id", "recommendations", ["supplier_id"], unique=False)
    op.create_index(
        "ix_recommendations_product_supplier_id",
        "recommendations",
        ["product_supplier_id"],
        unique=False,
    )
    op.create_index(
        "ix_recommendations_converted_purchase_order_id",
        "recommendations",
        ["converted_purchase_order_id"],
        unique=False,
    )
    op.create_index("ix_recommendations_recommendation_type", "recommendations", ["recommendation_type"], unique=False)
    op.create_index("ix_recommendations_status", "recommendations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recommendations_status", table_name="recommendations")
    op.drop_index("ix_recommendations_recommendation_type", table_name="recommendations")
    op.drop_index("ix_recommendations_converted_purchase_order_id", table_name="recommendations")
    op.drop_index("ix_recommendations_product_supplier_id", table_name="recommendations")
    op.drop_index("ix_recommendations_supplier_id", table_name="recommendations")
    op.drop_constraint(
        "fk_recommendations_converted_purchase_order_id_purchase_orders",
        "recommendations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_recommendations_product_supplier_id_product_suppliers",
        "recommendations",
        type_="foreignkey",
    )
    op.drop_constraint("fk_recommendations_supplier_id_suppliers", "recommendations", type_="foreignkey")

    op.drop_column("recommendations", "rejected_reason")
    op.drop_column("recommendations", "reviewed_by")
    op.drop_column("recommendations", "generated_by")
    op.drop_column("recommendations", "prompt_version")
    op.drop_column("recommendations", "model_name")
    op.drop_column("recommendations", "supplier_context_snapshot")
    op.drop_column("recommendations", "forecast_snapshot")
    op.drop_column("recommendations", "input_snapshot")
    op.drop_column("recommendations", "confidence")
    op.drop_column("recommendations", "reason")
    op.drop_column("recommendations", "currency")
    op.drop_column("recommendations", "estimated_total_cost")
    op.drop_column("recommendations", "estimated_unit_cost")
    op.drop_column("recommendations", "recommended_supplier_sku")
    op.drop_column("recommendations", "recommended_supplier_name")
    op.drop_column("recommendations", "status")
    op.drop_column("recommendations", "recommendation_type")
    op.drop_column("recommendations", "reviewed_at")
    op.drop_column("recommendations", "updated_at")
    op.drop_column("recommendations", "created_at")
    op.drop_column("recommendations", "converted_purchase_order_id")
    op.drop_column("recommendations", "product_supplier_id")
    op.drop_column("recommendations", "supplier_id")
