"""outcome tracking for agent recommendations

Revision ID: 0016_recommendation_outcomes
Revises: 0015_strategic_insights
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_recommendation_outcomes"
down_revision: Union[str, None] = "0015_strategic_insights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_status = sa.Enum(
    "pending", "positive", "negative", "neutral", "inconclusive",
    name="recommendation_outcome_status", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "recommendation_outcomes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.Integer,
            sa.ForeignKey("agent_recommendations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("tracked_object_type", sa.String(16), nullable=False),
        sa.Column("tracked_object_id", sa.Integer, nullable=False),
        sa.Column("status", _status, nullable=False, server_default="pending"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_recommendation_outcomes_status", "recommendation_outcomes", ["status"])


def downgrade() -> None:
    op.drop_table("recommendation_outcomes")
