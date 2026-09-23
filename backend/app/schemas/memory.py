"""Schemas for semantic memory facts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.semantic_memory import SemanticMemoryFact
from ..models.strategic_insight import StrategicInsight


class FactCreate(BaseModel):
    fact_text: str = Field(min_length=1, max_length=2000)
    fact_key: str | None = Field(default=None, max_length=120)
    relationship_id: int | None = None


class FactRejectRequest(BaseModel):
    reason: str | None = None


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    official_id: int
    relationship_id: int | None
    fact_text: str
    fact_key: str | None
    confidence: int | None
    verification_state: str
    source_type: str
    source_interaction_id: int | None
    created_by: int | None
    superseded_by_id: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, fact: SemanticMemoryFact) -> "FactOut":
        return cls(
            id=fact.id,
            official_id=fact.official_id,
            relationship_id=fact.relationship_id,
            fact_text=fact.fact_text,
            fact_key=fact.fact_key,
            confidence=fact.confidence,
            verification_state=fact.verification_state.value,
            source_type=fact.source_type,
            source_interaction_id=fact.source_interaction_id,
            created_by=fact.created_by,
            superseded_by_id=fact.superseded_by_id,
            created_at=fact.created_at,
            updated_at=fact.updated_at,
        )


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    official_id: int | None
    statement: str
    metric_type: str
    sample_size: int
    evidence: dict
    computed_at: datetime
    superseded: bool

    @classmethod
    def of(cls, insight: StrategicInsight) -> "InsightOut":
        return cls(
            id=insight.id,
            official_id=insight.official_id,
            statement=insight.statement,
            metric_type=insight.metric_type,
            sample_size=insight.sample_size,
            evidence=insight.evidence,
            computed_at=insight.computed_at,
            superseded=insight.superseded,
        )
