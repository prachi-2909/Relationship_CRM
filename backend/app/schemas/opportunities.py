"""Request/response models for the opportunity pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models.opportunity import OpportunityActivityType, OpportunityStage, OpportunityStatus


class OpportunityCreate(BaseModel):
    relationship_id: int
    title: str = Field(min_length=1, max_length=300)
    detail: str | None = None


class OpportunityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    detail: str | None = None
    status: OpportunityStatus | None = None


class OpportunityStageUpdate(BaseModel):
    stage: OpportunityStage
    outcome_note: str | None = Field(default=None, max_length=1000)


class OpportunityActivityCreate(BaseModel):
    type: OpportunityActivityType
    note: str = Field(min_length=1)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _no_system_type(self) -> "OpportunityActivityCreate":
        if self.type is OpportunityActivityType.STAGE_CHANGE:
            raise ValueError("stage_change is system-logged only")
        return self


class OpportunityActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_id: int
    type: OpportunityActivityType
    occurred_at: datetime
    note: str
    from_stage: OpportunityStage | None
    to_stage: OpportunityStage | None
    created_by: int | None
    created_at: datetime


class OpportunitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relationship_id: int
    official_id: int
    official_name: str
    title: str
    status: OpportunityStatus
    stage: OpportunityStage
    source: str
    source_interaction_id: int | None
    closed_at: datetime | None
    created_at: datetime

    @staticmethod
    def of(opp) -> "OpportunitySummary":
        return OpportunitySummary(
            id=opp.id,
            relationship_id=opp.relationship_id,
            official_id=opp.official_id,
            official_name=opp.relationship_ref.official.name,
            title=opp.title,
            status=opp.status,
            stage=opp.stage,
            source=opp.source,
            source_interaction_id=opp.source_interaction_id,
            closed_at=opp.closed_at,
            created_at=opp.created_at,
        )


class OpportunityDetail(OpportunitySummary):
    detail: str | None
    outcome_note: str | None
    created_by: int | None
    decided_by: int | None
    decided_at: datetime | None
    activities: list[OpportunityActivityOut]

    @staticmethod
    def of(opp) -> "OpportunityDetail":
        base = OpportunitySummary.of(opp).model_dump()
        return OpportunityDetail(
            **base,
            detail=opp.detail,
            outcome_note=opp.outcome_note,
            created_by=opp.created_by,
            decided_by=opp.decided_by,
            decided_at=opp.decided_at,
            activities=[OpportunityActivityOut.model_validate(a) for a in opp.activities],
        )


class OpportunityListResponse(BaseModel):
    items: list[OpportunitySummary]
    total: int
    limit: int
    offset: int
