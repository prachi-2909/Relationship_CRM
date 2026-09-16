"""opportunities: detection, pipeline, activities and outcomes

Revision ID: 0012_opportunities
Revises: 0011_agent_runs
Create Date: 2026-09-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_opportunities"
down_revision: Union[str, None] = "0011_agent_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_status = sa.Enum(
    "suggested", "confirmed", "dismissed",
    name="opportunity_status", native_enum=False, length=16,
)
_stage = sa.Enum(
    "identified", "qualified", "proposal", "negotiation", "won", "lost",
    name="opportunity_stage", native_enum=False, length=16,
)
_activity_type = sa.Enum(
    "email", "call", "meeting", "note", "stage_change",
    name="opportunity_activity_type", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "official_id", sa.Integer, sa.ForeignKey("officials.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("status", _status, nullable=False, server_default="suggested"),
        sa.Column("stage", _stage, nullable=False, server_default="identified"),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column(
            "source_interaction_id",
            sa.Integer,
            sa.ForeignKey("interactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "decided_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_note", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_opportunities_relationship_id", "opportunities", ["relationship_id"])
    op.create_index("ix_opportunities_official_id", "opportunities", ["official_id"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])
    op.create_index("ix_opportunities_stage", "opportunities", ["stage"])
    op.create_index(
        "ix_opportunities_source_interaction_id", "opportunities", ["source_interaction_id"]
    )

    op.create_table(
        "opportunity_activities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer,
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", _activity_type, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("from_stage", _stage, nullable=True),
        sa.Column("to_stage", _stage, nullable=True),
        sa.Column(
            "created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_opportunity_activities_opportunity_id", "opportunity_activities", ["opportunity_id"]
    )
    op.create_index("ix_opportunity_activities_type", "opportunity_activities", ["type"])
    op.create_index(
        "ix_opportunity_activities_occurred_at", "opportunity_activities", ["occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("opportunity_activities")
    op.drop_table("opportunities")
