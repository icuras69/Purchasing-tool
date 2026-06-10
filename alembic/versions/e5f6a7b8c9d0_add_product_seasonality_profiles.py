"""add product seasonality profiles

Revision ID: e5f6a7b8c9d0
Revises: b3c4d5e6f7a8
Create Date: 2026-06-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_seasonality_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("history_start", sa.Date(), nullable=True),
        sa.Column("history_end", sa.Date(), nullable=True),
        sa.Column("history_months", sa.Integer(), nullable=False),
        sa.Column("active_months", sa.Integer(), nullable=False),
        sa.Column("years_covered", sa.Integer(), nullable=False),
        sa.Column("total_units", sa.Float(), nullable=False),
        sa.Column("average_monthly_units", sa.Float(), nullable=False),
        sa.Column("monthly_units", sa.JSON(), nullable=True),
        sa.Column("monthly_indices", sa.JSON(), nullable=True),
        sa.Column("peak_months", sa.JSON(), nullable=True),
        sa.Column("low_months", sa.JSON(), nullable=True),
        sa.Column("primary_season", sa.String(length=50), nullable=True),
        sa.Column("seasonality_tag", sa.String(length=100), nullable=False),
        sa.Column("seasonality_strength", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_label", sa.String(length=50), nullable=False),
        sa.Column("coefficient_of_variation", sa.Float(), nullable=True),
        sa.Column("calculation_version", sa.String(length=50), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_product_seasonality_profiles_product_id"),
    )
    op.create_index(op.f("ix_product_seasonality_profiles_id"), "product_seasonality_profiles", ["id"], unique=False)
    op.create_index(
        op.f("ix_product_seasonality_profiles_product_id"),
        "product_seasonality_profiles",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_seasonality_profiles_seasonality_tag"),
        "product_seasonality_profiles",
        ["seasonality_tag"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_seasonality_profiles_confidence_label"),
        "product_seasonality_profiles",
        ["confidence_label"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_seasonality_profiles_confidence_label"), table_name="product_seasonality_profiles")
    op.drop_index(op.f("ix_product_seasonality_profiles_seasonality_tag"), table_name="product_seasonality_profiles")
    op.drop_index(op.f("ix_product_seasonality_profiles_product_id"), table_name="product_seasonality_profiles")
    op.drop_index(op.f("ix_product_seasonality_profiles_id"), table_name="product_seasonality_profiles")
    op.drop_table("product_seasonality_profiles")
