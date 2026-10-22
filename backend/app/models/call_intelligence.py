"""Mobile Call Intelligence: a Call Session is the technical event and can exist
without an official/relationship; a CRM Interaction is the verified business
record, created only after a human (the DC) reviews and confirms. Recording is
one of three co-equal input paths (Knowlarity recording / DC voice note /
manual text) - "RECORDING FAIL != INTERACTION FAIL" is the whole point of this
module, not an edge case bolted onto a recording-first design.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin
from .interaction import Direction


class CallSessionStatus(str, enum.Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    CONNECTED = "connected"
    ENDED = "ended"
    RECORDING = "recording"
    NO_RECORDING = "no_recording"
    UPLOAD_PENDING = "upload_pending"
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    CRM_LOGGED = "crm_logged"
    CANCELLED = "cancelled"
    RECORDING_UNAVAILABLE = "recording_unavailable"
    UPLOAD_FAILED = "upload_failed"
    TRANSCRIPTION_FAILED = "transcription_failed"
    ANALYSIS_FAILED = "analysis_failed"
    REVIEW_REJECTED = "review_rejected"
    CRM_WRITE_FAILED = "crm_write_failed"
    # Audio existed, was used (transcribed) or not, and has now been permanently deleted -
    # distinct from NO_RECORDING (no audio was ever captured in the first place).
    PURGED = "purged"


class IdentityStatus(str, enum.Enum):
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    POSSIBLE_IDENTITY = "possible_identity"
    VERIFIED_NEW_OFFICIAL = "verified_new_official"
    UNIDENTIFIED = "unidentified"
    # The number belongs to an active Kiosk Operator (CSP) - a known, registered
    # counterparty, just in the CSP directory rather than the Officials hierarchy.
    CSP = "csp"


_status = SAEnum(CallSessionStatus, native_enum=False, length=24, name="call_session_status")
_identity = SAEnum(IdentityStatus, native_enum=False, length=24, name="call_identity_status")
_direction = SAEnum(Direction, native_enum=False, length=16, name="call_direction")


class CallSession(Base, TimestampMixin):
    __tablename__ = "call_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    dc_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    direction: Mapped[Direction] = mapped_column(_direction, nullable=False)
    phone_ref: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    knowlarity_call_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    # "knowlarity" | "manual" (DC-typed number, still Knowlarity-routed) | "android_native"
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="knowlarity")
    # A locally-generated id the Android app creates when it arms a native call
    # attempt - idempotency for a retried completion report. Not unique (a retry
    # should update the same row, not collide like knowlarity_call_id would).
    native_call_ref: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # "carrier" (Knowlarity-reported, exact) | "device_estimated" (native mode:
    # OFFHOOK->IDLE elapsed time, which conflates ring-time and talk-time on a
    # non-privileged observer - never presented as carrier-precise).
    duration_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Which RecordingEngine (Android-side) attempted capture, and what it judged its own
    # capability to be - purely descriptive telemetry, not used for any access decision.
    recording_engine: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recording_capability_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    official_id: Mapped[int | None] = mapped_column(
        ForeignKey("officials.id", ondelete="SET NULL"), nullable=True, index=True
    )
    relationship_id: Mapped[int | None] = mapped_column(
        ForeignKey("relationships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Set when the number matches an active Kiosk Operator (CSP). A call is tied to
    # EITHER an official (hierarchy) OR a CSP (directory), never both.
    csp_id: Mapped[int | None] = mapped_column(
        ForeignKey("csps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recording_status: Mapped[CallSessionStatus] = mapped_column(
        _status, nullable=False, default=CallSessionStatus.INITIATED
    )
    identity_status: Mapped[IdentityStatus] = mapped_column(
        _identity, nullable=False, default=IdentityStatus.UNREGISTERED
    )
    processing_status: Mapped[CallSessionStatus] = mapped_column(
        _status, nullable=False, default=CallSessionStatus.INITIATED, index=True
    )
    interaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True
    )
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    official = relationship("Official", lazy="joined")
    csp = relationship("Csp", lazy="joined")
    dc_user = relationship("User", lazy="joined")
    recording: Mapped["CallRecording | None"] = relationship(
        back_populates="call_session", uselist=False, cascade="all, delete-orphan"
    )
    voice_note: Mapped["CallVoiceNote | None"] = relationship(
        back_populates="call_session", uselist=False, cascade="all, delete-orphan"
    )
    transcript: Mapped["CallTranscript | None"] = relationship(
        back_populates="call_session", uselist=False, cascade="all, delete-orphan"
    )
    analysis: Mapped["CallAIAnalysis | None"] = relationship(
        back_populates="call_session", uselist=False, cascade="all, delete-orphan"
    )
    identity_candidates: Mapped[list["CallIdentityCandidate"]] = relationship(
        back_populates="call_session", cascade="all, delete-orphan"
    )
    review: Mapped["CallReview | None"] = relationship(
        back_populates="call_session", uselist=False, cascade="all, delete-orphan"
    )


class CallRecording(Base, TimestampMixin):
    __tablename__ = "call_recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_session_id: Mapped[int] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "knowlarity" | "native"
    secure_object_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    call_session: Mapped[CallSession] = relationship(back_populates="recording")


class CallVoiceNote(Base, TimestampMixin):
    __tablename__ = "call_voice_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_session_id: Mapped[int] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    dc_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    secure_object_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    call_session: Mapped[CallSession] = relationship(back_populates="voice_note")


class CallTranscript(Base, TimestampMixin):
    __tablename__ = "call_transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_session_id: Mapped[int] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # recording|voice_note|manual_text
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="stub")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    call_session: Mapped[CallSession] = relationship(back_populates="transcript")


class CallAIAnalysis(Base, TimestampMixin):
    __tablename__ = "call_ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_session_id: Mapped[int] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(80), nullable=False, default="stub")
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1")
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1")
    analysis_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    call_session: Mapped[CallSession] = relationship(back_populates="analysis")


class CallIdentityCandidate(Base, TimestampMixin):
    __tablename__ = "call_identity_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_session_id: Mapped[int] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    candidate_official_id: Mapped[int | None] = mapped_column(
        ForeignKey("officials.id", ondelete="SET NULL"), nullable=True
    )
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    call_session: Mapped[CallSession] = relationship(back_populates="identity_candidates")


class CallReview(Base, TimestampMixin):
    __tablename__ = "call_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_session_id: Mapped[int] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    identity_action: Mapped[str] = mapped_column(String(24), nullable=False)  # link|create|keep_unidentified
    edited_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    call_session: Mapped[CallSession] = relationship(back_populates="review")
