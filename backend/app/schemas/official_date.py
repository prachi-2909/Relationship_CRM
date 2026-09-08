"""Request/response models for officials' dated facts."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.official import FieldVerification
from ..models.official_date import DateKind


class DateSet(BaseModel):
    value: date
    source: str = Field(min_length=1, max_length=255)
    confidence: int | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=500)


class OfficialDateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: DateKind
    value: date
    source: str
    confidence: int | None
    note: str | None
    verification_status: FieldVerification
    verified_by: int | None
    verified_at: datetime | None
