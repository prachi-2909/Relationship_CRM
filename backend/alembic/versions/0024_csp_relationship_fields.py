"""CSP relationship-building fields (birthday, gender, email, address) from KO details

Revision ID: 0024_csp_relationship_fields
Revises: 0023_csps
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_csp_relationship_fields"
down_revision: Union[str, None] = "0023_csps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("csps", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("csps", sa.Column("gender", sa.String(16), nullable=True))
    op.add_column("csps", sa.Column("email", sa.String(255), nullable=True))
    op.add_column("csps", sa.Column("address", sa.String(400), nullable=True))
    op.add_column("csps", sa.Column("pincode", sa.String(12), nullable=True))
    op.add_column("csps", sa.Column("home_phone", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("csps", "home_phone")
    op.drop_column("csps", "pincode")
    op.drop_column("csps", "address")
    op.drop_column("csps", "email")
    op.drop_column("csps", "gender")
    op.drop_column("csps", "date_of_birth")
