"""CSPs (customer service points) assigned to Relationship Managers

Revision ID: 0023_csps
Revises: 0022_recording_engine
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_csps"
down_revision: Union[str, None] = "0022_recording_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "csps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("csp_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("mobile", sa.String(32), nullable=True),
        sa.Column("alternate_mobile", sa.String(32), nullable=True),
        sa.Column("category", sa.String(40), nullable=True),
        sa.Column("rm_name", sa.String(120), nullable=False),
        sa.Column("rm_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("branch_name", sa.String(200), nullable=True),
        sa.Column("district", sa.String(120), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("lho", sa.String(120), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_csps_csp_id", "csps", ["csp_id"], unique=True)
    op.create_index("ix_csps_name", "csps", ["name"])
    op.create_index("ix_csps_rm_name", "csps", ["rm_name"])
    op.create_index("ix_csps_rm_user_id", "csps", ["rm_user_id"])


def downgrade() -> None:
    op.drop_index("ix_csps_rm_user_id", table_name="csps")
    op.drop_index("ix_csps_rm_name", table_name="csps")
    op.drop_index("ix_csps_name", table_name="csps")
    op.drop_index("ix_csps_csp_id", table_name="csps")
    op.drop_table("csps")
