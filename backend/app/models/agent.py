"""The autonomous agent: runs that observe relationships and produce
recommendations. Nothing here writes a real domain object directly — every
recommendation stays PENDING until a human approves it, at which point the
approval path calls the same service functions the rest of the app already
uses to create a task or draft a moment. See services/agent.py.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class AgentTrigger(str, enum.Enum):
    MANUAL = "manual"
    NIGHTLY = "nightly"


class AgentRunScope(str, enum.Enum):
    RELATIONSHIP = "relationship"
    PORTFOLIO = "portfolio"


class AgentRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RecommendationType(str, enum.Enum):
    """Mirrors the doc-specified agent tools relevant at this autonomy level:
    create_task(), create_draft() (a draft against an existing, already-
    detected EngagementMoment), and create_opportunity()."""

    CREATE_TASK = "create_task"
    DRAFT_MOMENT = "draft_moment"
    CREATE_OPPORTUNITY = "create_opportunity"


class RiskTier(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


_trigger = SAEnum(AgentTrigger, native_enum=False, length=16, name="agent_trigger")
_scope = SAEnum(AgentRunScope, native_enum=False, length=16, name="agent_run_scope")
_run_status = SAEnum(AgentRunStatus, native_enum=False, length=16, name="agent_run_status")
_rec_type = SAEnum(RecommendationType, native_enum=False, length=32, name="agent_recommendation_type")
_risk_tier = SAEnum(RiskTier, native_enum=False, length=8, name="agent_risk_tier")
_rec_status = SAEnum(
    RecommendationStatus, native_enum=False, length=16, name="agent_recommendation_status"
)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[AgentTrigger] = mapped_column(_trigger, nullable=False, index=True)
    scope: Mapped[AgentRunScope] = mapped_column(_scope, nullable=False)
    relationship_id: Mapped[int | None] = mapped_column(
        ForeignKey("relationships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        _run_status, nullable=False, default=AgentRunStatus.RUNNING, index=True
    )
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="stub")
    tools_used: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    relationships_considered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommendations_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendations: Mapped[list["AgentRecommendation"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentRecommendation.id",
    )


class AgentRecommendation(Base, TimestampMixin):
    __tablename__ = "agent_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    official_id: Mapped[int] = mapped_column(
        ForeignKey("officials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[RecommendationType] = mapped_column(_rec_type, nullable=False, index=True)
    risk_tier: Mapped[RiskTier] = mapped_column(_risk_tier, nullable=False, default=RiskTier.LOW)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[RecommendationStatus] = mapped_column(
        _rec_status, nullable=False, default=RecommendationStatus.PENDING, index=True
    )
    result_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="recommendations")
    official = relationship("Official", lazy="joined")
