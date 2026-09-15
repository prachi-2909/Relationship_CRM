"""officials.phone - a plain contact field, like email

Revision ID: 0010_official_phone
Revises: 0009_marriage_anniversary
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_official_phone"
down_revision: Union[str, None] = "0009_marriage_anniversary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("officials", sa.Column("phone", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("officials", "phone")
