"""add product seasonality backtests

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-10 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_seasonality_backtests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("readiness_status", sa.String(length=50), nullable=False),
        sa.Column("activation_recommendation", sa.String(length=100), nullable=False),
        sa.Column("seasonal_improvement_percent", sa.Float(), nullable=True),
        sa.Column("baseline_wape", sa.Float(), nullable=True),
        sa.Column("seasonal_wape", sa.Float(), nullable=True),
        sa.Column("baseline_mae", sa.Float(), nullable=True),
        sa.Column("seasonal_mae", sa.Float(), nullable=True),
        sa.Column("baseline_bias", sa.Float(), nullable=True),
        sa.Column("seasonal_bias", sa.Float(), nullable=True),
        sa.Column("evaluated_months", sa.Integer(), nullable=False),
        sa.Column("evaluated_years", sa.Integer(), nullable=False),
        sa.Column("recommended_max_multiplier", sa.Float(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("backtest_version", sa.String(length=50), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "backtest_version", name="uq_product_seasonality_backtest_product_version"),
    )
    op.create_index(op.f("ix_product_seasonality_backtests_id"), "product_seasonality_backtests", ["id"], unique=False)
    op.create_index(
        op.f("ix_product_seasonality_backtests_product_id"),
        "product_seasonality_backtests",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_seasonality_backtests_readiness_status"),
        "product_seasonality_backtests",
        ["readiness_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_seasonality_backtests_backtest_version"),
        "product_seasonality_backtests",
        ["backtest_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_seasonality_backtests_backtest_version"), table_name="product_seasonality_backtests")
    op.drop_index(op.f("ix_product_seasonality_backtests_readiness_status"), table_name="product_seasonality_backtests")
    op.drop_index(op.f("ix_product_seasonality_backtests_product_id"), table_name="product_seasonality_backtests")
    op.drop_index(op.f("ix_product_seasonality_backtests_id"), table_name="product_seasonality_backtests")
    op.drop_table("product_seasonality_backtests")
