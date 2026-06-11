"""add product forecast input profiles

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_forecast_input_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("cost_price", sa.Float(), nullable=True),
        sa.Column("cost_source", sa.String(length=100), nullable=False),
        sa.Column("cost_confidence", sa.String(length=50), nullable=False),
        sa.Column("cost_updated_at", sa.DateTime(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("lead_time_source", sa.String(length=100), nullable=False),
        sa.Column("lead_time_confidence", sa.String(length=50), nullable=False),
        sa.Column("min_order_qty", sa.Float(), nullable=True),
        sa.Column("moq_source", sa.String(length=100), nullable=False),
        sa.Column("pack_size", sa.Float(), nullable=True),
        sa.Column("pack_size_source", sa.String(length=100), nullable=False),
        sa.Column("safety_stock", sa.Float(), nullable=True),
        sa.Column("safety_stock_source", sa.String(length=100), nullable=False),
        sa.Column("blocking_issues", sa.JSON(), nullable=True),
        sa.Column("warning_issues", sa.JSON(), nullable=True),
        sa.Column("readiness_score", sa.Float(), nullable=False),
        sa.Column("calculation_version", sa.String(length=100), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index(op.f("ix_product_forecast_input_profiles_id"), "product_forecast_input_profiles", ["id"], unique=False)
    op.create_index(
        op.f("ix_product_forecast_input_profiles_product_id"),
        "product_forecast_input_profiles",
        ["product_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_forecast_input_profiles_product_id"), table_name="product_forecast_input_profiles")
    op.drop_index(op.f("ix_product_forecast_input_profiles_id"), table_name="product_forecast_input_profiles")
    op.drop_table("product_forecast_input_profiles")
