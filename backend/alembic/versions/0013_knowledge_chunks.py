"""RAG: knowledge chunks, and a sources column on ask_messages

Revision ID: 0013_knowledge_chunks
Revises: 0012_opportunities
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_knowledge_chunks"
down_revision: Union[str, None] = "0012_opportunities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Integer, nullable=False),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "official_id", sa.Integer, sa.ForeignKey("officials.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", sa.JSON, nullable=True),
        sa.Column("embedding_model", sa.String(80), nullable=False, server_default="stub"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("source_type", "source_id", "chunk_index", name="uq_knowledge_chunk_source"),
    )
    op.create_index("ix_knowledge_chunks_source_type", "knowledge_chunks", ["source_type"])
    op.create_index("ix_knowledge_chunks_relationship_id", "knowledge_chunks", ["relationship_id"])
    op.create_index("ix_knowledge_chunks_official_id", "knowledge_chunks", ["official_id"])

    with op.batch_alter_table("ask_messages") as batch_op:
        batch_op.add_column(sa.Column("sources", sa.JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ask_messages") as batch_op:
        batch_op.drop_column("sources")
    op.drop_table("knowledge_chunks")
