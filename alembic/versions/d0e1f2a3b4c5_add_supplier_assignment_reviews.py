"""add supplier assignment reviews

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_supplier_assignment_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("suggested_supplier_id", sa.Integer(), nullable=True),
        sa.Column("suggestion_source", sa.String(length=100), nullable=True),
        sa.Column("confidence_label", sa.String(length=50), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("evidence_summary", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("reviewed_supplier_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["reviewed_supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["suggested_supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index(
        op.f("ix_product_supplier_assignment_reviews_id"),
        "product_supplier_assignment_reviews",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_supplier_assignment_reviews_product_id"),
        "product_supplier_assignment_reviews",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_supplier_assignment_reviews_suggested_supplier_id"),
        "product_supplier_assignment_reviews",
        ["suggested_supplier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_supplier_assignment_reviews_reviewed_supplier_id"),
        "product_supplier_assignment_reviews",
        ["reviewed_supplier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_supplier_assignment_reviews_suggestion_source"),
        "product_supplier_assignment_reviews",
        ["suggestion_source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_supplier_assignment_reviews_confidence_label"),
        "product_supplier_assignment_reviews",
        ["confidence_label"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_supplier_assignment_reviews_status"),
        "product_supplier_assignment_reviews",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_supplier_assignment_reviews_status"), table_name="product_supplier_assignment_reviews")
    op.drop_index(op.f("ix_product_supplier_assignment_reviews_confidence_label"), table_name="product_supplier_assignment_reviews")
    op.drop_index(op.f("ix_product_supplier_assignment_reviews_suggestion_source"), table_name="product_supplier_assignment_reviews")
    op.drop_index(op.f("ix_product_supplier_assignment_reviews_reviewed_supplier_id"), table_name="product_supplier_assignment_reviews")
    op.drop_index(op.f("ix_product_supplier_assignment_reviews_suggested_supplier_id"), table_name="product_supplier_assignment_reviews")
    op.drop_index(op.f("ix_product_supplier_assignment_reviews_product_id"), table_name="product_supplier_assignment_reviews")
    op.drop_index(op.f("ix_product_supplier_assignment_reviews_id"), table_name="product_supplier_assignment_reviews")
    op.drop_table("product_supplier_assignment_reviews")
