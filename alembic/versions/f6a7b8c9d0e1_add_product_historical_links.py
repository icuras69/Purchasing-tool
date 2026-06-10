"""add product historical links

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_historical_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orderpro_product_id", sa.Integer(), nullable=False),
        sa.Column("historical_product_id", sa.Integer(), nullable=False),
        sa.Column("match_method", sa.String(length=50), nullable=False),
        sa.Column("match_value", sa.String(length=255), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_label", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["historical_product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["orderpro_product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "orderpro_product_id",
            "historical_product_id",
            name="uq_product_historical_links_pair",
        ),
    )
    op.create_index(op.f("ix_product_historical_links_id"), "product_historical_links", ["id"], unique=False)
    op.create_index(
        op.f("ix_product_historical_links_orderpro_product_id"),
        "product_historical_links",
        ["orderpro_product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_historical_links_historical_product_id"),
        "product_historical_links",
        ["historical_product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_historical_links_match_value"),
        "product_historical_links",
        ["match_value"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_historical_links_status"),
        "product_historical_links",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_historical_links_status"), table_name="product_historical_links")
    op.drop_index(op.f("ix_product_historical_links_match_value"), table_name="product_historical_links")
    op.drop_index(op.f("ix_product_historical_links_historical_product_id"), table_name="product_historical_links")
    op.drop_index(op.f("ix_product_historical_links_orderpro_product_id"), table_name="product_historical_links")
    op.drop_index(op.f("ix_product_historical_links_id"), table_name="product_historical_links")
    op.drop_table("product_historical_links")
