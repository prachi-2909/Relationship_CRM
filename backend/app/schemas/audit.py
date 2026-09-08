"""Response model for the audit-log viewer."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    action: str
    entity_type: str
    entity_id: str | None
    before: dict | None
    after: dict | None
    at: datetime


class AuditListResponse(BaseModel):
    items: list[AuditEntry]
    total: int
    limit: int
    offset: int
