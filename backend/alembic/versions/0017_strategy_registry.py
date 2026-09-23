"""strategy registry and controlled experiments

Revision ID: 0017_strategy_registry
Revises: 0016_recommendation_outcomes
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_strategy_registry"
down_revision: Union[str, None] = "0016_recommendation_outcomes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_strategy_status = sa.Enum(
    "draft", "testing", "active", "retired", name="strategy_status", native_enum=False, length=16,
)
_version_status = sa.Enum(
    "draft", "testing", "active", "retired", "rejected",
    name="strategy_version_status", native_enum=False, length=16,
)
_experiment_status = sa.Enum(
    "draft", "running", "completed", "aborted", name="experiment_status", native_enum=False, length=16,
)
_arm = sa.Enum("control", "treatment", name="experiment_arm", native_enum=False, length=16)


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("strategy_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        # not a DB-enforced FK - see models/strategy.py's comment on the circular reference
        sa.Column("current_version_id", sa.Integer, nullable=True),
        sa.Column("status", _strategy_status, nullable=False, server_default="draft"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "strategy_id", sa.Integer, sa.ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("evaluation_metrics", sa.JSON, nullable=True),
        sa.Column("experiment_metadata", sa.JSON, nullable=True),
        sa.Column("status", _version_status, nullable=False, server_default="draft"),
        sa.Column(
            "created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "approved_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"])

    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "strategy_id", sa.Integer, sa.ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "control_version_id",
            sa.Integer,
            sa.ForeignKey("strategy_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "treatment_version_id",
            sa.Integer,
            sa.ForeignKey("strategy_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", _experiment_status, nullable=False, server_default="draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minimum_sample_size", sa.Integer, nullable=False, server_default="20"),
        sa.Column(
            "created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_experiments_strategy_id", "experiments", ["strategy_id"])

    op.create_table(
        "experiment_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "experiment_id", sa.Integer, sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("arm", _arm, nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("experiment_id", "relationship_id", name="uq_experiment_relationship"),
    )
    op.create_index("ix_experiment_assignments_experiment_id", "experiment_assignments", ["experiment_id"])
    op.create_index("ix_experiment_assignments_relationship_id", "experiment_assignments", ["relationship_id"])


def downgrade() -> None:
    op.drop_table("experiment_assignments")
    op.drop_table("experiments")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
