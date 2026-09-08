"""Request/response models for the officials import flow."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.data_import import ImportStatus, RowAction


class ImportCreate(BaseModel):
    """Paste-CSV path. The multipart upload path is a separate endpoint."""

    filename: str = Field(min_length=1, max_length=255)
    csv_text: str = Field(min_length=1)


class ImportRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    raw: dict
    normalized: dict
    resolved_official_id: int | None
    action: RowAction
    confidence: int
    error: str | None


class ImportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: ImportStatus
    row_count: int
    accepted_count: int
    rejected_count: int
    committed_at: datetime | None
    created_at: datetime


class WorkedSample(BaseModel):
    action: RowAction
    row_number: int
    official_name: str
    writes: dict


class ImportPreview(ImportSummary):
    rows: list[ImportRowOut]
    samples: list[WorkedSample]
