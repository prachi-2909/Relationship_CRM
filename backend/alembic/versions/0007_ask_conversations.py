"""supervisor conversations - short-term memory for /ask

Revision ID: 0007_ask_conversations
Revises: 0006_connections
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_ask_conversations"
down_revision: Union[str, None] = "0006_connections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_role = sa.Enum(
    "user", "assistant", name="ask_message_role", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "ask_conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=True),
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
        "ix_ask_conversations_user_id", "ask_conversations", ["user_id"]
    )

    op.create_table(
        "ask_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("ask_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", _role, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("scope", sa.String(16), nullable=True),
        sa.Column("generated_by", sa.String(64), nullable=True),
        sa.Column("considered", sa.JSON, nullable=True),
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
        "ix_ask_messages_conversation_id", "ask_messages", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_table("ask_messages")
    op.drop_table("ask_conversations")
