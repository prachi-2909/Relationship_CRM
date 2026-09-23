"""strategic memory: evidence-backed insights

Revision ID: 0015_strategic_insights
Revises: 0014_semantic_memory
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_strategic_insights"
down_revision: Union[str, None] = "0014_semantic_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategic_insights",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column(
            "official_id", sa.Integer, sa.ForeignKey("officials.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_strategic_insights_official_id", "strategic_insights", ["official_id"])
    op.create_index("ix_strategic_insights_metric_type", "strategic_insights", ["metric_type"])


def downgrade() -> None:
    op.drop_table("strategic_insights")
