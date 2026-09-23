"""mobile call intelligence: call sessions, recordings, voice notes, transcripts, AI analyses, identity candidates, reviews

Revision ID: 0018_call_intelligence
Revises: 0017_strategy_registry
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_call_intelligence"
down_revision: Union[str, None] = "0017_strategy_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_call_status = sa.Enum(
    "initiated", "ringing", "connected", "ended", "recording", "no_recording",
    "upload_pending", "uploaded", "transcribing", "analyzing", "review_required",
    "approved", "crm_logged", "cancelled", "recording_unavailable", "upload_failed",
    "transcription_failed", "analysis_failed", "review_rejected", "crm_write_failed",
    name="call_session_status", native_enum=False, length=24,
)
_identity_status = sa.Enum(
    "registered", "unregistered", "possible_identity", "verified_new_official", "unidentified",
    name="call_identity_status", native_enum=False, length=24,
)
_direction = sa.Enum(
    "inbound", "outbound", "internal", name="call_direction", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "call_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dc_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", _direction, nullable=False),
        sa.Column("phone_ref", sa.String(32), nullable=False),
        sa.Column("knowlarity_call_id", sa.String(80), nullable=True, unique=True),
        sa.Column("channel", sa.String(16), nullable=False, server_default="knowlarity"),
        sa.Column("official_id", sa.Integer, sa.ForeignKey("officials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("relationship_id", sa.Integer, sa.ForeignKey("relationships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("recording_status", _call_status, nullable=False, server_default="initiated"),
        sa.Column("identity_status", _identity_status, nullable=False, server_default="unregistered"),
        sa.Column("processing_status", _call_status, nullable=False, server_default="initiated"),
        sa.Column("interaction_id", sa.Integer, sa.ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_call_sessions_dc_user_id", "call_sessions", ["dc_user_id"])
    op.create_index("ix_call_sessions_phone_ref", "call_sessions", ["phone_ref"])
    op.create_index("ix_call_sessions_official_id", "call_sessions", ["official_id"])
    op.create_index("ix_call_sessions_relationship_id", "call_sessions", ["relationship_id"])
    op.create_index("ix_call_sessions_processing_status", "call_sessions", ["processing_status"])

    op.create_table(
        "call_recordings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("call_session_id", sa.Integer, sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("secure_object_ref", sa.String(500), nullable=False),
        sa.Column("format", sa.String(16), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("checksum", sa.String(80), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "call_voice_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("call_session_id", sa.Integer, sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("dc_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("secure_object_ref", sa.String(500), nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "call_transcripts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("call_session_id", sa.Integer, sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="stub"),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "call_ai_analyses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("call_session_id", sa.Integer, sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("model_version", sa.String(80), nullable=False, server_default="stub"),
        sa.Column("prompt_version", sa.String(40), nullable=False, server_default="1"),
        sa.Column("schema_version", sa.String(40), nullable=False, server_default="1"),
        sa.Column("analysis_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "call_identity_candidates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("call_session_id", sa.Integer, sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_official_id", sa.Integer, sa.ForeignKey("officials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("confidence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_call_identity_candidates_call_session_id", "call_identity_candidates", ["call_session_id"])

    op.create_table(
        "call_reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("call_session_id", sa.Integer, sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("identity_action", sa.String(24), nullable=False),
        sa.Column("edited_payload", sa.JSON, nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("call_reviews")
    op.drop_table("call_identity_candidates")
    op.drop_table("call_ai_analyses")
    op.drop_table("call_transcripts")
    op.drop_table("call_voice_notes")
    op.drop_table("call_recordings")
    op.drop_table("call_sessions")
