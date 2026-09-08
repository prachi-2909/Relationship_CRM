"""Request/response models for engagement moments."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.engagement_moment import MomentStatus, MomentType


class MomentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    official_id: int
    official_name: str
    relationship_id: int
    type: MomentType
    event_date: date | None
    status: MomentStatus
    suppressed_reason: str | None
    created_at: datetime

    @staticmethod
    def of(moment) -> "MomentSummary":
        return MomentSummary(
            id=moment.id,
            official_id=moment.official_id,
            official_name=moment.official.name,
            relationship_id=moment.relationship_id,
            type=moment.type,
            event_date=moment.event_date,
            status=moment.status,
            suppressed_reason=moment.suppressed_reason,
            created_at=moment.created_at,
        )


class MomentDetail(MomentSummary):
    evidence: dict
    draft_text: str | None
    decided_by: int | None
    decided_at: datetime | None

    @staticmethod
    def of(moment) -> "MomentDetail":
        base = MomentSummary.of(moment).model_dump()
        return MomentDetail(
            **base,
            evidence=moment.evidence,
            draft_text=moment.draft_text,
            decided_by=moment.decided_by,
            decided_at=moment.decided_at,
        )


class MomentListResponse(BaseModel):
    items: list[MomentSummary]
    total: int
    limit: int
    offset: int


class DraftUpdate(BaseModel):
    draft_text: str = Field(min_length=1)


class DismissRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class SentRequest(BaseModel):
    outcome: str | None = Field(default=None, max_length=500)
