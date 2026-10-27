"""Explicit outcome feedback on relationship-intelligence suggestions.

An RM or DC can say whether a suggested talking point was useful or a suggested follow-up was relevant.
This table is the *only* place that signal lives, and it is written only by an explicit human action:
a call happening, a brief being confirmed or a commitment being created is never recorded here as
"this recommendation was right". Every row snapshots the suggestion text and kind as the server
generated it (not as the client sent it), so quality can still be measured after the wording changes.

Plain strings (not SQLAlchemy Enums) for the categorical columns, on purpose: Enum columns store member
NAMES, which has already caused one lowercase-default bug in this codebase.
"""

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

TARGET_TALKING_POINT = "talking_point"
TARGET_FOLLOWUP = "followup"
# verdicts allowed per target type
VERDICTS = {
    TARGET_TALKING_POINT: ("useful", "not_useful"),
    TARGET_FOLLOWUP: ("relevant", "not_relevant"),
}
POSITIVE_VERDICTS = {"useful", "relevant"}

SUBJECT_CSP = "csp"
SUBJECT_OFFICIAL = "official"


class IntelligenceFeedback(Base, TimestampMixin):
    __tablename__ = "intelligence_feedback"
    __table_args__ = (
        # One verdict per person per suggestion; changing your mind updates the row.
        UniqueConstraint("user_id", "subject_type", "subject_id", "target_type", "target_key",
                         name="uq_intelligence_feedback_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    subject_type: Mapped[str] = mapped_column(String(10), nullable=False)   # csp | official
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_key: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)   # e.g. check_theirs
    text: Mapped[str] = mapped_column(String(500), nullable=False)             # snapshot, server-side
    verdict: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
