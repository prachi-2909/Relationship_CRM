"""Strategy registry and controlled experiments.

A Strategy names something the agent's behavior can vary on (e.g. follow-up
timing). Each StrategyVersion is one concrete configuration of it - a rule
parameter set or a prompt variant. Nothing here is applied automatically:
an experiment assigns specific relationships to a control/treatment version,
and promoting a version to active requires an explicit, sample-size-gated
admin approval (see services/strategy.py::promote). An unassigned
relationship's agent behavior is completely unaffected by any of this.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class StrategyStatus(str, enum.Enum):
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    RETIRED = "retired"


class StrategyVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    RETIRED = "retired"
    REJECTED = "rejected"


class ExperimentStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"


class ExperimentArm(str, enum.Enum):
    CONTROL = "control"
    TREATMENT = "treatment"


_strategy_status = SAEnum(StrategyStatus, native_enum=False, length=16, name="strategy_status")
_version_status = SAEnum(
    StrategyVersionStatus, native_enum=False, length=16, name="strategy_version_status"
)
_experiment_status = SAEnum(ExperimentStatus, native_enum=False, length=16, name="experiment_status")
_arm = SAEnum(ExperimentArm, native_enum=False, length=16, name="experiment_arm")


class Strategy(Base, TimestampMixin):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    # Not a DB-enforced FK: strategy_versions.strategy_id already points the
    # other way, and SQLite can't create two tables with a circular FK in
    # one migration. Integrity is maintained by services/strategy.py alone.
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[StrategyStatus] = mapped_column(
        _strategy_status, nullable=False, default=StrategyStatus.DRAFT
    )

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.version",
    )


class StrategyVersion(Base, TimestampMixin):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    evaluation_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    experiment_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[StrategyVersionStatus] = mapped_column(
        _version_status, nullable=False, default=StrategyVersionStatus.DRAFT
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    strategy: Mapped[Strategy] = relationship(back_populates="versions")


class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    control_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    treatment_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ExperimentStatus] = mapped_column(
        _experiment_status, nullable=False, default=ExperimentStatus.DRAFT
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    minimum_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    assignments: Mapped[list["ExperimentAssignment"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentAssignment(Base, TimestampMixin):
    __tablename__ = "experiment_assignments"
    __table_args__ = (UniqueConstraint("experiment_id", "relationship_id", name="uq_experiment_relationship"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), nullable=False, index=True
    )
    arm: Mapped[ExperimentArm] = mapped_column(_arm, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    experiment: Mapped[Experiment] = relationship(back_populates="assignments")
