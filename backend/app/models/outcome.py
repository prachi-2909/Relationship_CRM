"""Recommendation outcomes: what actually happened after a recommendation
was approved. Extends AgentRecommendation (joined via result_ref) rather
than replacing it - result_ref still records what was created; this table
tracks what happened to it afterwards.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class OutcomeStatus(str, enum.Enum):
    PENDING = "pending"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    INCONCLUSIVE = "inconclusive"


_status = SAEnum(OutcomeStatus, native_enum=False, length=16, name="recommendation_outcome_status")


class RecommendationOutcome(Base, TimestampMixin):
    __tablename__ = "recommendation_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_recommendations.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tracked_object_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "task" | "moment" | "opportunity"
    tracked_object_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OutcomeStatus] = mapped_column(_status, nullable=False, default=OutcomeStatus.PENDING, index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    recommendation = relationship("AgentRecommendation", lazy="joined")
