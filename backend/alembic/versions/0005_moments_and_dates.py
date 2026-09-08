"""official dates and engagement moments

Revision ID: 0005_moments_and_dates
Revises: 0004_tasks_and_imports
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_moments_and_dates"
down_revision: Union[str, None] = "0004_tasks_and_imports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_date_kind = sa.Enum(
    "birthday", "joined", "promoted", name="official_date_kind",
    native_enum=False, length=16,
)
_date_verif = sa.Enum(
    "unverified", "verified", name="official_date_verification",
    native_enum=False, length=16,
)
_moment_type = sa.Enum(
    "promotion", "birthday", "work_anniversary", "inactivity",
    name="moment_type", native_enum=False, length=20,
)
_moment_status = sa.Enum(
    "detected", "draft_ready", "approved", "sent_manually", "dismissed",
    name="moment_status", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "official_dates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", _date_kind, nullable=False),
        sa.Column("value", sa.Date, nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Integer, nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "verification_status", _date_verif, nullable=False, server_default="unverified"
        ),
        sa.Column(
            "verified_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_official_dates_official_id", "official_dates", ["official_id"])
    op.create_index("ix_official_dates_kind", "official_dates", ["kind"])

    op.create_table(
        "engagement_moments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", _moment_type, nullable=False),
        sa.Column("event_date", sa.Date, nullable=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("status", _moment_status, nullable=False, server_default="detected"),
        sa.Column("draft_text", sa.Text, nullable=True),
        sa.Column("suppressed_reason", sa.String(200), nullable=True),
        sa.Column(
            "decided_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_engagement_moments_official_id", "engagement_moments", ["official_id"]
    )
    op.create_index(
        "ix_engagement_moments_relationship_id", "engagement_moments", ["relationship_id"]
    )
    op.create_index("ix_engagement_moments_type", "engagement_moments", ["type"])
    op.create_index("ix_engagement_moments_status", "engagement_moments", ["status"])


def downgrade() -> None:
    op.drop_table("engagement_moments")
    op.drop_table("official_dates")
