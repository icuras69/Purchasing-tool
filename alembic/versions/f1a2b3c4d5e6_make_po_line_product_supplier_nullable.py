"""make po line product supplier nullable

Revision ID: f1a2b3c4d5e6
Revises: e9a7b6c5d4f3
Create Date: 2026-06-01 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e9a7b6c5d4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "purchase_order_lines",
        "product_supplier_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "purchase_order_lines",
        "product_supplier_id",
        existing_type=sa.Integer(),
        nullable=False,
        existing_nullable=True,
    )
