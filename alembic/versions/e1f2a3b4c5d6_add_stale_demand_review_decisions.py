"""add stale demand review decisions

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stale_demand_review_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=50), nullable=False),
        sa.Column("reviewed_by", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index(
        op.f("ix_stale_demand_review_decisions_id"),
        "stale_demand_review_decisions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stale_demand_review_decisions_product_id"),
        "stale_demand_review_decisions",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stale_demand_review_decisions_recommendation_id"),
        "stale_demand_review_decisions",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stale_demand_review_decisions_decision"),
        "stale_demand_review_decisions",
        ["decision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stale_demand_review_decisions_decision"), table_name="stale_demand_review_decisions")
    op.drop_index(op.f("ix_stale_demand_review_decisions_recommendation_id"), table_name="stale_demand_review_decisions")
    op.drop_index(op.f("ix_stale_demand_review_decisions_product_id"), table_name="stale_demand_review_decisions")
    op.drop_index(op.f("ix_stale_demand_review_decisions_id"), table_name="stale_demand_review_decisions")
    op.drop_table("stale_demand_review_decisions")
