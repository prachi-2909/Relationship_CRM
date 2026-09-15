"""Request/response models for the Supervisor's ask endpoint and its
conversations (short-term memory: the running transcript of one thread)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    # omit to start a new conversation; pass back the id from a prior
    # response to continue it (a follow-up question can then be resolved
    # against what was just discussed)
    conversation_id: int | None = None


class Considered(BaseModel):
    relationship_id: int
    official_name: str


class AskResponse(BaseModel):
    conversation_id: int
    answer: str
    generated_by: str
    scope: str  # "targeted" | "portfolio"
    considered: list[Considered]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    scope: str | None
    generated_by: str | None
    considered: list[Considered] | None
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]
