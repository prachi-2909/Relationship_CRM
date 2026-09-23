"""semantic memory: durable facts about an official

Revision ID: 0014_semantic_memory
Revises: 0013_knowledge_chunks
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_semantic_memory"
down_revision: Union[str, None] = "0013_knowledge_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_verif = sa.Enum(
    "unverified", "human_confirmed", "human_rejected", "superseded",
    name="semantic_verification_state", native_enum=False, length=24,
)


def upgrade() -> None:
    op.create_table(
        "semantic_memory_facts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "official_id", sa.Integer, sa.ForeignKey("officials.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("fact_text", sa.Text, nullable=False),
        sa.Column("fact_key", sa.String(120), nullable=True),
        sa.Column("confidence", sa.Integer, nullable=True),
        sa.Column("verification_state", _verif, nullable=False, server_default="unverified"),
        sa.Column("source_type", sa.String(32), nullable=False),
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
            "superseded_by_id",
            sa.Integer,
            sa.ForeignKey("semantic_memory_facts.id", ondelete="SET NULL"),
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
    op.create_index("ix_semantic_memory_facts_official_id", "semantic_memory_facts", ["official_id"])
    op.create_index("ix_semantic_memory_facts_fact_key", "semantic_memory_facts", ["fact_key"])


def downgrade() -> None:
    op.drop_table("semantic_memory_facts")
