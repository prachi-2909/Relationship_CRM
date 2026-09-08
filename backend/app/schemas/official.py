"""Request/response models for officials and per-field provenance."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.official import (
    FieldVerification,
    OfficialStatus,
    VerificationStatus,
)


class OfficialBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    designation: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    level: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    organization_unit_id: int | None = None


class OfficialCreate(OfficialBase):
    pass


class OfficialUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    designation: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    level: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    organization_unit_id: int | None = None
    status: OfficialStatus | None = None


class FieldProvenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    source: str
    confidence: int | None
    note: str | None
    verification_status: FieldVerification
    verified_by: int | None
    verified_at: datetime | None
    updated_at: datetime


class SetFieldRequest(BaseModel):
    value: str | int | None = None
    source: str = Field(min_length=1, max_length=255)
    confidence: int | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=500)


class OfficialSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    designation: str | None
    level: str | None
    location: str | None
    organization_unit_id: int | None
    status: OfficialStatus
    verification_status: VerificationStatus


class OfficialDetail(OfficialSummary):
    department: str | None
    fields: dict[str, FieldProvenanceOut] = {}


class OfficialListResponse(BaseModel):
    items: list[OfficialSummary]
    total: int
    limit: int
    offset: int


class TimelineEntry(BaseModel):
    action: str
    entity_type: str
    at: datetime
    actor_id: int | None
    before: dict | None
    after: dict | None
