"""Relationships: one per official, with a computed health score and history."""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class RelationshipStatus(str, enum.Enum):
    NEW = "new"
    DEVELOPING = "developing"
    ACTIVE = "active"
    STRONG = "strong"
    STRATEGIC = "strategic"
    DECLINING = "declining"
    AT_RISK = "at_risk"
    INACTIVE = "inactive"


class Importance(str, enum.Enum):
    ROUTINE = "routine"
    IMPORTANT = "important"
    STRATEGIC = "strategic"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_status = SAEnum(
    RelationshipStatus, native_enum=False, length=16, name="relationship_status"
)
_importance = SAEnum(Importance, native_enum=False, length=16, name="relationship_importance")
_risk = SAEnum(RiskLevel, native_enum=False, length=8, name="relationship_risk")


class Relationship(Base, TimestampMixin):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[RelationshipStatus] = mapped_column(
        _status, nullable=False, default=RelationshipStatus.NEW, index=True
    )
    importance: Mapped[Importance] = mapped_column(
        _importance, nullable=False, default=Importance.ROUTINE, index=True
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        _risk, nullable=False, default=RiskLevel.HIGH, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    official = relationship("Official", lazy="joined")
    score_history: Mapped[list["RelationshipScoreHistory"]] = relationship(
        back_populates="relationship_ref",
        cascade="all, delete-orphan",
        order_by="RelationshipScoreHistory.computed_at.desc()",
    )


class RelationshipScoreHistory(Base):
    __tablename__ = "relationship_score_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    components: Mapped[dict] = mapped_column(JSON, nullable=False)
    weights_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    relationship_ref: Mapped[Relationship] = relationship(back_populates="score_history")
