"""Commitments — the actionable promises pulled out of a call, tracked to closure.

A call's AI brief lists commitments and action items as free text; this turns each one into a
discrete, trackable record with an owner, an optional due date and a status, so "approved
information" becomes work the team actually follows up on, and open items surface again before the
next call (pre-call intelligence).

One commitment belongs to EITHER a CSP (an RM-KO call) OR an official (a DC-SBI call), never both.
`source_kind` records which, because the two streams carry different retention, permission and audit
rules: RM-KO recordings are retained, DC-SBI audio is discarded after logging - but the commitment
text itself is a CRM record in both cases.
"""

import enum
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class CommitmentParty(str, enum.Enum):
    OURS = "ours"        # the RM / DC promised to do something
    THEIRS = "theirs"    # the CSP / official promised to do something
    MUTUAL = "mutual"    # agreed jointly / unclear which side


class CommitmentStatus(str, enum.Enum):
    # Suggested by the AI from a call brief; NOT an obligation until a human accepts it.
    PROPOSED = "proposed"
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class CommitmentSourceKind(str, enum.Enum):
    """Which call stream the commitment came from - drives retention, permissions and audit."""
    RM_CSP = "rm_csp"          # Relationship Manager <-> Kiosk Operator (recordings retained)
    DC_OFFICIAL = "dc_official"  # Data Collector <-> SBI official (audio discarded after logging)


_party = SAEnum(CommitmentParty, native_enum=False, length=12, name="commitment_party")
_status = SAEnum(CommitmentStatus, native_enum=False, length=12, name="commitment_status")
_source_kind = SAEnum(CommitmentSourceKind, native_enum=False, length=16, name="commitment_source_kind")


class Commitment(Base, TimestampMixin):
    __tablename__ = "commitments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The call this commitment was extracted from (or logged against). Kept even if the call's audio
    # is later purged - the commitment text is a durable CRM record.
    call_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Exactly one of csp_id / official_id is set.
    csp_id: Mapped[int | None] = mapped_column(
        ForeignKey("csps.id", ondelete="CASCADE"), nullable=True, index=True
    )
    official_id: Mapped[int | None] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), nullable=True, index=True
    )
    relationship_id: Mapped[int | None] = mapped_column(
        ForeignKey("relationships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The staff member responsible for the counterparty (the RM or DC) - who should action it.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    party: Mapped[CommitmentParty] = mapped_column(_party, nullable=False, default=CommitmentParty.OURS)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[CommitmentStatus] = mapped_column(
        _status, nullable=False, default=CommitmentStatus.OPEN, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="call_brief")  # call_brief | manual
    source_kind: Mapped[CommitmentSourceKind] = mapped_column(_source_kind, nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- near-duplicate review (a human decides; nothing is ever merged silently) ---
    # The earlier commitment this one looks like (set at extraction when the wording is similar).
    possible_duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("commitments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # None = never flagged | "flagged" = awaiting a human | "separate" = human said different |
    # "merged" = human said same (this row was closed into merged_into_id; it is kept, not deleted).
    duplicate_review: Mapped[str | None] = mapped_column(String(12), nullable=True)
    merged_into_id: Mapped[int | None] = mapped_column(
        ForeignKey("commitments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    csp = relationship("Csp", lazy="joined")
    official = relationship("Official", lazy="joined")

    possible_duplicate_of = relationship(
        "Commitment", remote_side="Commitment.id", foreign_keys="Commitment.possible_duplicate_of_id",
        lazy="select", viewonly=True,
    )


class CommitmentEvent(Base):
    """One entry in a commitment's own history: proposed, accepted, dismissed, done, merged, ...

    Kept per commitment so the acceptance/dismissal trail survives a merge and is readable without
    digging through the global audit log. `detail` holds ids and small scalars only - never the
    commitment text - so retention of the text is governed solely by the commitment row. A commitment
    that is purged takes its events with it."""

    __tablename__ = "commitment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    commitment_id: Mapped[int] = mapped_column(
        ForeignKey("commitments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
