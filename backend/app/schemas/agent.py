"""Request/response models for the autonomous agent."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.agent import (
    AgentRunScope,
    AgentRunStatus,
    AgentTrigger,
    RecommendationStatus,
    RecommendationType,
    RiskTier,
)


class RunTriggerRequest(BaseModel):
    scope: AgentRunScope
    relationship_id: int | None = None


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class AgentRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: AgentTrigger
    scope: AgentRunScope
    relationship_id: int | None
    requested_by: int | None
    status: AgentRunStatus
    model: str
    relationships_considered: int
    recommendations_created: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None

    @staticmethod
    def of(run) -> "AgentRunSummary":
        return AgentRunSummary(
            id=run.id,
            trigger=run.trigger,
            scope=run.scope,
            relationship_id=run.relationship_id,
            requested_by=run.requested_by,
            status=run.status,
            model=run.model,
            relationships_considered=run.relationships_considered,
            recommendations_created=run.recommendations_created,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=run.duration_ms,
            error=run.error,
        )


class AgentRunDetail(AgentRunSummary):
    tools_used: list[str]
    recommendations: list["RecommendationSummary"]

    @staticmethod
    def of(run) -> "AgentRunDetail":
        base = AgentRunSummary.of(run).model_dump()
        return AgentRunDetail(
            **base,
            tools_used=run.tools_used,
            recommendations=[RecommendationSummary.of(r) for r in run.recommendations],
        )


class AgentRunListResponse(BaseModel):
    items: list[AgentRunSummary]
    total: int
    limit: int
    offset: int


class RecommendationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    relationship_id: int
    official_id: int
    official_name: str
    type: RecommendationType
    risk_tier: RiskTier
    reasoning: str
    status: RecommendationStatus
    created_at: datetime
    expires_at: datetime | None

    @staticmethod
    def of(rec) -> "RecommendationSummary":
        return RecommendationSummary(
            id=rec.id,
            run_id=rec.run_id,
            relationship_id=rec.relationship_id,
            official_id=rec.official_id,
            official_name=rec.official.name,
            type=rec.type,
            risk_tier=rec.risk_tier,
            reasoning=rec.reasoning,
            status=rec.status,
            created_at=rec.created_at,
            expires_at=rec.expires_at,
        )


class RecommendationDetail(RecommendationSummary):
    evidence: dict
    payload: dict
    result_ref: dict | None
    decided_by: int | None
    decided_at: datetime | None

    @staticmethod
    def of(rec) -> "RecommendationDetail":
        base = RecommendationSummary.of(rec).model_dump()
        return RecommendationDetail(
            **base,
            evidence=rec.evidence,
            payload=rec.payload,
            result_ref=rec.result_ref,
            decided_by=rec.decided_by,
            decided_at=rec.decided_at,
        )


class RecommendationListResponse(BaseModel):
    items: list[RecommendationSummary]
    total: int
    limit: int
    offset: int


AgentRunDetail.model_rebuild()
