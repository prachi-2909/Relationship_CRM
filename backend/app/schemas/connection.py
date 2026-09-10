"""Request/response models for the stakeholder graph."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from ..models.connection import ConnectionStatus, ConnectionType


class ConnectionCreate(BaseModel):
    from_official_id: int
    to_official_id: int
    type: ConnectionType
    note: str | None = None

    @model_validator(mode="after")
    def _distinct(self) -> "ConnectionCreate":
        if self.from_official_id == self.to_official_id:
            raise ValueError("a connection needs two different officials")
        return self


class ConnectionUpdate(BaseModel):
    status: ConnectionStatus | None = None
    note: str | None = None


class OfficialRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    level: str | None


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ConnectionType
    status: ConnectionStatus
    source: str
    source_interaction_id: int | None
    confidence: int | None
    note: str | None
    from_official: OfficialRef
    to_official: OfficialRef
    created_at: datetime
    decided_at: datetime | None


class Neighbor(BaseModel):
    connection_id: int
    official_id: int
    name: str
    level: str | None
    type: ConnectionType
    direction: str  # outgoing | incoming | mutual
    status: ConnectionStatus
    label: str
    note: str | None
    source: str


class OfficialGraph(BaseModel):
    official_id: int
    confirmed: list[Neighbor]
    suggested: list[Neighbor]
