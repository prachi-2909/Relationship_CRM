"""Strategic memory: evidence-backed insights computed from real historical
outcome data - never an LLM guess. Old rows are kept (superseded, not
deleted) so trend history comes for free.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class StrategicInsight(Base, TimestampMixin):
    __tablename__ = "strategic_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "official" | "portfolio"
    official_id: Mapped[int | None] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), nullable=True, index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
