"""track last birthday wish sent per CSP

Revision ID: 0025_csp_birthday_wish
Revises: 0024_csp_relationship_fields
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_csp_birthday_wish"
down_revision: Union[str, None] = "0024_csp_relationship_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("csps", sa.Column("last_birthday_wish_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("csps", "last_birthday_wish_on")
