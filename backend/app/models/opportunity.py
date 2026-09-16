"""Opportunities: detection, pipeline, activities and outcomes.

Detection mirrors the stakeholder-connection graph exactly - a manual entry
lands CONFIRMED, something the extractor pulled out of an interaction note
lands SUGGESTED and waits for a human. ``stage`` only progresses once an
opportunity is CONFIRMED.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class OpportunityStatus(str, enum.Enum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class OpportunityStage(str, enum.Enum):
    IDENTIFIED = "identified"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class OpportunityActivityType(str, enum.Enum):
    EMAIL = "email"
    CALL = "call"
    MEETING = "meeting"
    NOTE = "note"
    STAGE_CHANGE = "stage_change"  # system-logged only, never accepted from the API


_status = SAEnum(OpportunityStatus, native_enum=False, length=16, name="opportunity_status")
_stage = SAEnum(OpportunityStage, native_enum=False, length=16, name="opportunity_stage")
_activity_type = SAEnum(
    OpportunityActivityType, native_enum=False, length=16, name="opportunity_activity_type"
)


class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OpportunityStatus] = mapped_column(
        _status, nullable=False, default=OpportunityStatus.SUGGESTED, index=True
    )
    stage: Mapped[OpportunityStage] = mapped_column(
        _stage, nullable=False, default=OpportunityStage.IDENTIFIED, index=True
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_interaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    relationship_ref = relationship("Relationship", lazy="joined")
    activities: Mapped[list["OpportunityActivity"]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
        order_by="OpportunityActivity.occurred_at.desc()",
    )


class OpportunityActivity(Base, TimestampMixin):
    __tablename__ = "opportunity_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[OpportunityActivityType] = mapped_column(_activity_type, nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    from_stage: Mapped[OpportunityStage | None] = mapped_column(_stage, nullable=True)
    to_stage: Mapped[OpportunityStage | None] = mapped_column(_stage, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="activities")
