"""autonomous agent: runs and recommendations

Revision ID: 0011_agent_runs
Revises: 0010_official_phone
Create Date: 2026-09-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_agent_runs"
down_revision: Union[str, None] = "0010_official_phone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_trigger = sa.Enum(
    "manual", "nightly", name="agent_trigger", native_enum=False, length=16,
)
_run_scope = sa.Enum(
    "relationship", "portfolio", name="agent_run_scope", native_enum=False, length=16,
)
_run_status = sa.Enum(
    "running", "completed", "failed", name="agent_run_status", native_enum=False, length=16,
)
_rec_type = sa.Enum(
    "create_task", "draft_moment",
    name="agent_recommendation_type", native_enum=False, length=32,
)
_risk_tier = sa.Enum(
    "low", "medium", "high", name="agent_risk_tier", native_enum=False, length=8,
)
_rec_status = sa.Enum(
    "pending", "approved", "rejected", "expired",
    name="agent_recommendation_status", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trigger", _trigger, nullable=False),
        sa.Column("scope", _run_scope, nullable=False),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requested_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", _run_status, nullable=False, server_default="running"),
        sa.Column("model", sa.String(80), nullable=False, server_default="stub"),
        sa.Column("tools_used", sa.JSON, nullable=False),
        sa.Column("relationships_considered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("recommendations_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_runs_trigger", "agent_runs", ["trigger"])
    op.create_index("ix_agent_runs_relationship_id", "agent_runs", ["relationship_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "agent_recommendations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id", sa.Integer, sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "official_id", sa.Integer, sa.ForeignKey("officials.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("type", _rec_type, nullable=False),
        sa.Column("risk_tier", _risk_tier, nullable=False, server_default="low"),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", _rec_status, nullable=False, server_default="pending"),
        sa.Column("result_ref", sa.JSON, nullable=True),
        sa.Column(
            "decided_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_recommendations_run_id", "agent_recommendations", ["run_id"])
    op.create_index(
        "ix_agent_recommendations_relationship_id", "agent_recommendations", ["relationship_id"]
    )
    op.create_index("ix_agent_recommendations_official_id", "agent_recommendations", ["official_id"])
    op.create_index("ix_agent_recommendations_type", "agent_recommendations", ["type"])
    op.create_index("ix_agent_recommendations_status", "agent_recommendations", ["status"])


def downgrade() -> None:
    op.drop_table("agent_recommendations")
    op.drop_table("agent_runs")
