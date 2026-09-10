"""Request/response models for relationships and their score history."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.relationship import Importance, RelationshipStatus, RiskLevel


class RelationshipCreate(BaseModel):
    official_id: int
    owner_id: int | None = None


class RelationshipUpdate(BaseModel):
    # importance is derived (level + engagement sentiment); it is not set here
    status: RelationshipStatus | None = None
    owner_id: int | None = None
    next_action_at: datetime | None = None


class OfficialRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    designation: str | None
    level: str | None
    organization_unit_id: int | None


class RelationshipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    official_id: int
    official_name: str
    official_level: str | None
    owner_id: int | None
    status: RelationshipStatus
    importance: Importance
    risk_level: RiskLevel
    score: int
    last_interaction_at: datetime | None
    next_action_at: datetime | None

    @staticmethod
    def of(rel) -> "RelationshipSummary":
        return RelationshipSummary(
            id=rel.id,
            official_id=rel.official_id,
            official_name=rel.official.name,
            official_level=rel.official.level,
            owner_id=rel.owner_id,
            status=rel.status,
            importance=rel.importance,
            risk_level=rel.risk_level,
            score=rel.score,
            last_interaction_at=rel.last_interaction_at,
            next_action_at=rel.next_action_at,
        )


class RelationshipDetail(RelationshipSummary):
    official: OfficialRef
    score_components: dict | None = None


class RelationshipListResponse(BaseModel):
    items: list[RelationshipSummary]
    total: int
    limit: int
    offset: int


class ScoreHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: int
    components: dict
    weights_version: str
    reason: str | None
    computed_at: datetime
