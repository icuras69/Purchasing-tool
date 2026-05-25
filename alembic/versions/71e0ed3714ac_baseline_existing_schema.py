"""baseline existing schema

Revision ID: 71e0ed3714ac
Revises: 
Create Date: 2026-05-25 13:42:22.735626+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = '71e0ed3714ac'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
