"""Engagement moments: detected relationship events that may warrant a courteous
touch. Everything stops at a human-approved draft — there is no send path.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class MomentType(str, enum.Enum):
    PROMOTION = "promotion"
    BIRTHDAY = "birthday"
    WORK_ANNIVERSARY = "work_anniversary"
    INACTIVITY = "inactivity"


class MomentStatus(str, enum.Enum):
    DETECTED = "detected"
    DRAFT_READY = "draft_ready"
    APPROVED = "approved"
    SENT_MANUALLY = "sent_manually"
    DISMISSED = "dismissed"


_type = SAEnum(MomentType, native_enum=False, length=20, name="moment_type")
_status = SAEnum(MomentStatus, native_enum=False, length=16, name="moment_status")


class EngagementMoment(Base, TimestampMixin):
    __tablename__ = "engagement_moments"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[MomentType] = mapped_column(_type, nullable=False, index=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[MomentStatus] = mapped_column(
        _status, nullable=False, default=MomentStatus.DETECTED, index=True
    )
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suppressed_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    official = relationship("Official", lazy="joined")
