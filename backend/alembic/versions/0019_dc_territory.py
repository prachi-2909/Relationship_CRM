"""dc territory: which organisation units a DC covers

Revision ID: 0019_dc_territory
Revises: 0018_call_intelligence
Create Date: 2026-09-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_dc_territory"
down_revision: Union[str, None] = "0018_call_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dc_territories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dc_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_unit_id", sa.Integer, sa.ForeignKey("organization_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("dc_user_id", "organization_unit_id", name="uq_dc_territory_dc_unit"),
    )
    op.create_index("ix_dc_territories_dc_user_id", "dc_territories", ["dc_user_id"])
    op.create_index("ix_dc_territories_organization_unit_id", "dc_territories", ["organization_unit_id"])


def downgrade() -> None:
    op.drop_table("dc_territories")
