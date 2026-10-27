"""commitments: trackable promises extracted from call briefs

Turns the free-text commitments/action-items in a call's AI brief into discrete, trackable records
(owner, due date, status) for both RM-KO and DC-SBI calls. source_kind keeps the two streams
separable for retention, permission and audit controls.

Revision ID: 0027_commitments
Revises: 0026_call_csp_link
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_commitments"
down_revision: Union[str, None] = "0026_call_csp_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commitments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_session_id", sa.Integer(), sa.ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("csp_id", sa.Integer(), sa.ForeignKey("csps.id", ondelete="CASCADE"), nullable=True),
        sa.Column("official_id", sa.Integer(), sa.ForeignKey("officials.id", ondelete="CASCADE"), nullable=True),
        sa.Column("relationship_id", sa.Integer(), sa.ForeignKey("relationships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text", sa.String(length=500), nullable=False),
        # No server_default on the enum-backed columns: SQLAlchemy stores enum NAMES ("OURS", "OPEN"),
        # so a lowercase DB default would be unreadable. The model supplies the defaults.
        sa.Column("party", sa.String(length=12), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="call_brief"),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_commitments_call_session_id", "commitments", ["call_session_id"])
    op.create_index("ix_commitments_csp_id", "commitments", ["csp_id"])
    op.create_index("ix_commitments_official_id", "commitments", ["official_id"])
    op.create_index("ix_commitments_relationship_id", "commitments", ["relationship_id"])
    op.create_index("ix_commitments_owner_user_id", "commitments", ["owner_user_id"])
    op.create_index("ix_commitments_due_date", "commitments", ["due_date"])
    op.create_index("ix_commitments_status", "commitments", ["status"])
    op.create_index("ix_commitments_source_kind", "commitments", ["source_kind"])


def downgrade() -> None:
    op.drop_table("commitments")
