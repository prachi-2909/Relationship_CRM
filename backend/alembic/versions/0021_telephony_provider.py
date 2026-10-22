"""telephony provider: native_call_ref + duration_source on call_sessions

Revision ID: 0021_telephony_provider
Revises: 0020_user_presence
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_telephony_provider"
down_revision: Union[str, None] = "0020_user_presence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "call_sessions",
        sa.Column("native_call_ref", sa.String(80), nullable=True),
    )
    op.create_index(
        "ix_call_sessions_native_call_ref", "call_sessions", ["native_call_ref"]
    )
    op.add_column(
        "call_sessions",
        sa.Column("duration_source", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("call_sessions", "duration_source")
    op.drop_index("ix_call_sessions_native_call_ref", table_name="call_sessions")
    op.drop_column("call_sessions", "native_call_ref")
