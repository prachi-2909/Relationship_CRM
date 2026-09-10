"""person-to-person connections between officials

Revision ID: 0006_connections
Revises: 0005_moments_and_dates
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_connections"
down_revision: Union[str, None] = "0005_moments_and_dates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_conn_type = sa.Enum(
    "reports_to", "works_with", "introduced_by",
    name="connection_type", native_enum=False, length=20,
)
_conn_status = sa.Enum(
    "suggested", "confirmed", "dismissed",
    name="connection_status", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "from_official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", _conn_type, nullable=False),
        sa.Column("status", _conn_status, nullable=False, server_default="suggested"),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column(
            "source_interaction_id",
            sa.Integer,
            sa.ForeignKey("interactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Integer, nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.UniqueConstraint(
            "from_official_id", "to_official_id", "type",
            name="uq_connection_pair_type",
        ),
        sa.CheckConstraint(
            "from_official_id <> to_official_id", name="ck_connection_not_self"
        ),
    )
    op.create_index(
        "ix_connections_from_official_id", "connections", ["from_official_id"]
    )
    op.create_index("ix_connections_to_official_id", "connections", ["to_official_id"])
    op.create_index("ix_connections_type", "connections", ["type"])
    op.create_index("ix_connections_status", "connections", ["status"])


def downgrade() -> None:
    op.drop_table("connections")
