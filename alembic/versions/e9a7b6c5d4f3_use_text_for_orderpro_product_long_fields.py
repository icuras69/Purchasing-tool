"""use text for orderpro product long fields

Revision ID: e9a7b6c5d4f3
Revises: d4f7a2c9e8b1
Create Date: 2026-06-01 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9a7b6c5d4f3"
down_revision: Union[str, None] = "d4f7a2c9e8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "products",
        "description",
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "products",
        "image_url",
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "products",
        "image_url",
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
    op.alter_column(
        "products",
        "description",
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=True,
    )
