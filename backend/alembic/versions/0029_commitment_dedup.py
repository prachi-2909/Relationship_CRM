"""commitments: near-duplicate review links and a per-commitment event history

Adds possible_duplicate_of_id / duplicate_review / merged_into_id to commitments (a human reviews a
flagged near-duplicate; nothing is merged silently) and commitment_events, which keeps each
commitment's own accept/dismiss/done/merge trail.

Revision ID: 0029_commitment_dedup
Revises: 0028_media_deletions
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_commitment_dedup"
down_revision: Union[str, None] = "0028_media_deletions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("commitments") as batch:
        batch.add_column(sa.Column("possible_duplicate_of_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("duplicate_review", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("merged_into_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_commitments_possible_duplicate_of", "commitments", ["possible_duplicate_of_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_commitments_merged_into", "commitments", ["merged_into_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_commitments_possible_duplicate_of_id", ["possible_duplicate_of_id"])
        batch.create_index("ix_commitments_merged_into_id", ["merged_into_id"])

    op.create_table(
        "commitment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("commitment_id", sa.Integer(), sa.ForeignKey("commitments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_commitment_events_commitment_id", "commitment_events", ["commitment_id"])


def downgrade() -> None:
    op.drop_table("commitment_events")
    with op.batch_alter_table("commitments") as batch:
        batch.drop_index("ix_commitments_merged_into_id")
        batch.drop_index("ix_commitments_possible_duplicate_of_id")
        batch.drop_constraint("fk_commitments_merged_into", type_="foreignkey")
        batch.drop_constraint("fk_commitments_possible_duplicate_of", type_="foreignkey")
        batch.drop_column("merged_into_id")
        batch.drop_column("duplicate_review")
        batch.drop_column("possible_duplicate_of_id")
