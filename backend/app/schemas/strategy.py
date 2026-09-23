"""Schemas for the strategy registry, versions, and controlled experiments."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StrategyCreate(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=64)


class StrategyVersionCreate(BaseModel):
    config: dict


class ExperimentCreate(BaseModel):
    control_version_id: int
    treatment_version_id: int
    relationship_ids: list[int]
    minimum_sample_size: int = 20


class StrategyVersionOut(BaseModel):
    id: int
    strategy_id: int
    version: int
    config: dict
    evaluation_metrics: dict | None
    experiment_metadata: dict | None
    status: str
    created_by: int | None
    approved_by: int | None
    approved_at: datetime | None
    created_at: datetime

    @staticmethod
    def of(v) -> "StrategyVersionOut":
        return StrategyVersionOut(
            id=v.id, strategy_id=v.strategy_id, version=v.version, config=v.config,
            evaluation_metrics=v.evaluation_metrics, experiment_metadata=v.experiment_metadata,
            status=v.status.value, created_by=v.created_by, approved_by=v.approved_by,
            approved_at=v.approved_at, created_at=v.created_at,
        )


class StrategyOut(BaseModel):
    id: int
    strategy_id: str
    name: str
    category: str
    current_version_id: int | None
    status: str
    versions: list[StrategyVersionOut]

    @staticmethod
    def of(s) -> "StrategyOut":
        return StrategyOut(
            id=s.id, strategy_id=s.strategy_id, name=s.name, category=s.category,
            current_version_id=s.current_version_id, status=s.status.value,
            versions=[StrategyVersionOut.of(v) for v in s.versions],
        )


class ExperimentAssignmentOut(BaseModel):
    relationship_id: int
    arm: str


class ExperimentOut(BaseModel):
    id: int
    strategy_id: int
    control_version_id: int
    treatment_version_id: int
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    minimum_sample_size: int
    assignments: list[ExperimentAssignmentOut]

    @staticmethod
    def of(e) -> "ExperimentOut":
        return ExperimentOut(
            id=e.id, strategy_id=e.strategy_id, control_version_id=e.control_version_id,
            treatment_version_id=e.treatment_version_id, status=e.status.value,
            started_at=e.started_at, ended_at=e.ended_at, minimum_sample_size=e.minimum_sample_size,
            assignments=[ExperimentAssignmentOut(relationship_id=a.relationship_id, arm=a.arm.value) for a in e.assignments],
        )
