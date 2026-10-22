"""recording engine + capability status on call_sessions, PURGED status value

Revision ID: 0022_recording_engine
Revises: 0021_telephony_provider
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_recording_engine"
down_revision: Union[str, None] = "0021_telephony_provider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("call_sessions", sa.Column("recording_engine", sa.String(40), nullable=True))
    op.add_column("call_sessions", sa.Column("recording_capability_status", sa.String(24), nullable=True))
    # PURGED is a new value of the existing non-native (String-backed) status enum column -
    # no column-level change needed for SQLite/Postgres text storage.


def downgrade() -> None:
    op.drop_column("call_sessions", "recording_capability_status")
    op.drop_column("call_sessions", "recording_engine")
