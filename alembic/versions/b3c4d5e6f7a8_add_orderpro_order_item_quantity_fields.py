"""add orderpro order item quantity fields

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-08 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orderpro_order_items", sa.Column("quantity_ordered", sa.Float(), nullable=True))
    op.add_column("orderpro_order_items", sa.Column("quantity_picked", sa.Float(), nullable=True))
    op.add_column("orderpro_order_items", sa.Column("quantity_shipped", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("orderpro_order_items", "quantity_shipped")
    op.drop_column("orderpro_order_items", "quantity_picked")
    op.drop_column("orderpro_order_items", "quantity_ordered")
