"""Request/response models for interactions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.interaction import Direction, InteractionType, Sentiment


class InteractionCreate(BaseModel):
    relationship_id: int
    type: InteractionType
    direction: Direction = Direction.INTERNAL
    occurred_at: datetime | None = None
    channel: str | None = Field(default=None, max_length=120)
    raw_notes: str = Field(min_length=1)


class InteractionUpdate(BaseModel):
    type: InteractionType | None = None
    direction: Direction | None = None
    occurred_at: datetime | None = None
    channel: str | None = Field(default=None, max_length=120)
    raw_notes: str | None = Field(default=None, min_length=1)
    # Human override of the effective structured extraction / sentiment.
    structured: dict | None = None
    sentiment: Sentiment | None = None


class InteractionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relationship_id: int
    official_id: int
    type: InteractionType
    direction: Direction
    occurred_at: datetime
    channel: str | None
    sentiment: Sentiment
    ai_summary: str | None


class InteractionDetail(InteractionSummary):
    raw_notes: str
    ai_structured: dict | None
    ai_model: str | None
    structured: dict | None
    created_by: int | None
    created_at: datetime


class InteractionListResponse(BaseModel):
    items: list[InteractionSummary]
    total: int
    limit: int
    offset: int


class EmailParseRequest(BaseModel):
    raw_email: str = Field(min_length=1)


class ParsedEmailOut(BaseModel):
    from_name: str | None
    from_email: str | None
    to: list[str]
    date: datetime | None
    subject: str | None
    body: str
    quoted_removed: bool
    matched_official_id: int | None
    matched_official_name: str | None
    matched_relationship_id: int | None
