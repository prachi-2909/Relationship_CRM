"""user presence: is the DC app in the foreground right now

Revision ID: 0020_user_presence
Revises: 0019_dc_territory
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_user_presence"
down_revision: Union[str, None] = "0019_dc_territory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_app_foreground", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_active_at")
    op.drop_column("users", "is_app_foreground")
