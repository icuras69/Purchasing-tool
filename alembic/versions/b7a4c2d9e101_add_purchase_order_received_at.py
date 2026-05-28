"""add purchase order received timestamp

Revision ID: b7a4c2d9e101
Revises: 9c1d4e8f2a34
Create Date: 2026-05-28 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7a4c2d9e101"
down_revision: Union[str, None] = "9c1d4e8f2a34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("received_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("purchase_orders", "received_at")
