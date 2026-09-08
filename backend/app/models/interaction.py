"""Interactions: the logged contact record, plus AI-extracted structure kept
separate from the human-edited version and from the untouched raw notes.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class InteractionType(str, enum.Enum):
    EMAIL = "email"
    CALL = "call"
    MEETING = "meeting"
    NOTE = "note"


class Direction(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class Sentiment(str, enum.Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


_type = SAEnum(InteractionType, native_enum=False, length=16, name="interaction_type")
_direction = SAEnum(Direction, native_enum=False, length=16, name="interaction_direction")
_sentiment = SAEnum(Sentiment, native_enum=False, length=16, name="interaction_sentiment")


class Interaction(Base, TimestampMixin):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[InteractionType] = mapped_column(_type, nullable=False, index=True)
    direction: Mapped[Direction] = mapped_column(
        _direction, nullable=False, default=Direction.INTERNAL
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    channel: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Untouched source text — only ever changed by an explicit edit.
    raw_notes: Mapped[str] = mapped_column(Text, nullable=False)

    # Model output. Replaced wholesale on reprocess.
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_structured: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Effective values: seeded from the model, then human-editable. Kept across reprocess.
    structured: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sentiment: Mapped[Sentiment] = mapped_column(
        _sentiment, nullable=False, default=Sentiment.UNKNOWN, index=True
    )

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    relationship_ref = relationship("Relationship", lazy="joined")
