"""Semantic memory: durable, open-ended facts about an official, extracted
from interaction text or entered by hand.

Distinct from OfficialFieldProvenance (official.py), which already owns the
closed schema of PROVENANCED_FIELDS (designation/department/level/location/
org unit) - this is for facts with no dedicated column (preferences, stated
goals, communication style). Also distinct from episodic memory
(agent.py::_recent_history), which is agent-action history keyed by
(relationship_id, recommendation_type) - a different axis entirely.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class SemanticVerificationState(str, enum.Enum):
    UNVERIFIED = "unverified"
    HUMAN_CONFIRMED = "human_confirmed"
    HUMAN_REJECTED = "human_rejected"
    SUPERSEDED = "superseded"


_verif = SAEnum(
    SemanticVerificationState, native_enum=False, length=24, name="semantic_verification_state"
)


class SemanticMemoryFact(Base, TimestampMixin):
    __tablename__ = "semantic_memory_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_id: Mapped[int | None] = mapped_column(
        ForeignKey("relationships.id", ondelete="SET NULL"), nullable=True
    )
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    fact_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_state: Mapped[SemanticVerificationState] = mapped_column(
        _verif, nullable=False, default=SemanticVerificationState.UNVERIFIED
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_interaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("semantic_memory_facts.id", ondelete="SET NULL"), nullable=True
    )

    official = relationship("Official", lazy="joined")
