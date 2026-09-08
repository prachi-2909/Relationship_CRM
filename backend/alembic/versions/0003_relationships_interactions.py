"""relationships, score history, interactions

Revision ID: 0003_relationships_interactions
Revises: 0002_organisation
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_relationships_interactions"
down_revision: Union[str, None] = "0002_organisation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_rel_status = sa.Enum(
    "new", "developing", "active", "strong", "strategic", "declining", "at_risk",
    "inactive", name="relationship_status", native_enum=False, length=16,
)
_importance = sa.Enum(
    "routine", "important", "strategic", name="relationship_importance",
    native_enum=False, length=16,
)
_risk = sa.Enum(
    "low", "medium", "high", name="relationship_risk", native_enum=False, length=8
)
_itype = sa.Enum(
    "email", "call", "meeting", "note", name="interaction_type",
    native_enum=False, length=16,
)
_idir = sa.Enum(
    "inbound", "outbound", "internal", name="interaction_direction",
    native_enum=False, length=16,
)
_isent = sa.Enum(
    "positive", "neutral", "negative", "unknown", name="interaction_sentiment",
    native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", _rel_status, nullable=False, server_default="new"),
        sa.Column("importance", _importance, nullable=False, server_default="routine"),
        sa.Column("risk_level", _risk, nullable=False, server_default="high"),
        sa.Column("score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_relationships_official_id", "relationships", ["official_id"], unique=True
    )
    op.create_index("ix_relationships_owner_id", "relationships", ["owner_id"])
    op.create_index("ix_relationships_status", "relationships", ["status"])
    op.create_index("ix_relationships_importance", "relationships", ["importance"])
    op.create_index("ix_relationships_risk_level", "relationships", ["risk_level"])
    op.create_index("ix_relationships_score", "relationships", ["score"])

    op.create_table(
        "relationship_score_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("components", sa.JSON, nullable=False),
        sa.Column("weights_version", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(120), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_relationship_score_history_relationship_id",
        "relationship_score_history",
        ["relationship_id"],
    )
    op.create_index(
        "ix_relationship_score_history_computed_at",
        "relationship_score_history",
        ["computed_at"],
    )

    op.create_table(
        "interactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", _itype, nullable=False),
        sa.Column("direction", _idir, nullable=False, server_default="internal"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(120), nullable=True),
        sa.Column("raw_notes", sa.Text, nullable=False),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("ai_structured", sa.JSON, nullable=True),
        sa.Column("ai_model", sa.String(80), nullable=True),
        sa.Column("structured", sa.JSON, nullable=True),
        sa.Column("sentiment", _isent, nullable=False, server_default="unknown"),
        sa.Column(
            "created_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        "ix_interactions_relationship_id", "interactions", ["relationship_id"]
    )
    op.create_index("ix_interactions_official_id", "interactions", ["official_id"])
    op.create_index("ix_interactions_type", "interactions", ["type"])
    op.create_index("ix_interactions_occurred_at", "interactions", ["occurred_at"])
    op.create_index("ix_interactions_sentiment", "interactions", ["sentiment"])


def downgrade() -> None:
    op.drop_table("interactions")
    op.drop_table("relationship_score_history")
    op.drop_index("ix_relationships_official_id", table_name="relationships")
    op.drop_table("relationships")
