"""intelligence_feedback: explicit useful / relevant verdicts on suggestions

Revision ID: 0030_intelligence_feedback
Revises: 0029_commitment_dedup
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_intelligence_feedback"
down_revision: Union[str, None] = "0029_commitment_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intelligence_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("subject_type", sa.String(length=10), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_key", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "subject_type", "subject_id", "target_type", "target_key",
            name="uq_intelligence_feedback_once",
        ),
    )
    op.create_index("ix_intelligence_feedback_user_id", "intelligence_feedback", ["user_id"])
    op.create_index("ix_intelligence_feedback_subject_id", "intelligence_feedback", ["subject_id"])
    op.create_index("ix_intelligence_feedback_target_type", "intelligence_feedback", ["target_type"])
    op.create_index("ix_intelligence_feedback_kind", "intelligence_feedback", ["kind"])
    op.create_index("ix_intelligence_feedback_verdict", "intelligence_feedback", ["verdict"])


def downgrade() -> None:
    op.drop_table("intelligence_feedback")
