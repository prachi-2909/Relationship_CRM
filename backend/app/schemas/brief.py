"""Response model for the read-only Relationship Brief."""

from __future__ import annotations

from pydantic import BaseModel


class BriefInteraction(BaseModel):
    occurred_at: str
    type: str
    direction: str
    sentiment: str
    summary: str


class BriefFollowup(BaseModel):
    title: str
    due_at: str | None
    overdue: bool


class BriefMoment(BaseModel):
    type: str
    status: str
    trigger: str | None
    suppressed: bool


class BriefDate(BaseModel):
    kind: str
    date: str
    in_days: int


class ReconnectOpportunity(BaseModel):
    yes: bool
    reason: str


class BriefConnection(BaseModel):
    official_id: int
    name: str
    level: str | None
    type: str
    direction: str
    label: str
    note: str | None


class Stakeholders(BaseModel):
    available: bool
    note: str
    connections: list[BriefConnection]
    suggested_count: int
    mentioned: list[str]


class RelationshipBrief(BaseModel):
    relationship_id: int
    official_name: str
    official_level: str | None
    unit: str | None
    owner_id: int | None
    status: str
    importance: str
    score: int
    band: str
    days_since_last_contact: int | None

    narrative: str
    generated_by: str

    what_is_important: str
    what_changed: list[str]
    reconnect_opportunity: ReconnectOpportunity
    next_interaction: str
    stakeholders: Stakeholders

    open_followups: list[BriefFollowup]
    recent_commitments: list[str]
    open_moments: list[BriefMoment]
    upcoming_dates: list[BriefDate]
    recent_interactions: list[BriefInteraction]
