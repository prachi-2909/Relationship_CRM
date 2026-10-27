"""media deletion outbox: queued, retried, audited file deletions

Revision ID: 0028_media_deletions
Revises: 0027_commitments
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_media_deletions"
down_revision: Union[str, None] = "0027_commitments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_deletions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("secure_object_ref", sa.String(length=500), nullable=False),
        sa.Column("reason", sa.String(length=60), nullable=False),
        # status is a plain string, so a lowercase default is correct here (no Enum name mapping).
        sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_media_deletions_secure_object_ref", "media_deletions", ["secure_object_ref"])
    op.create_index("ix_media_deletions_status", "media_deletions", ["status"])
    op.create_index("ix_media_deletions_next_attempt_at", "media_deletions", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_table("media_deletions")
