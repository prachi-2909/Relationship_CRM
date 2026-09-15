"""Request/response models for the Supervisor's ask endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Considered(BaseModel):
    relationship_id: int
    official_name: str


class AskResponse(BaseModel):
    answer: str
    generated_by: str
    scope: str  # "targeted" | "portfolio"
    considered: list[Considered]
