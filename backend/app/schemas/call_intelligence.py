"""Schemas for the Mobile Call Intelligence module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.call_intelligence import CallSession


class OutgoingCallRequest(BaseModel):
    official_id: int


class ManualTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class LinkOfficialRequest(BaseModel):
    official_id: int
    update_phone: bool = False


class CreateOfficialRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    designation: str | None = None
    department: str | None = None
    level: str | None = None
    location: str | None = None


class ConfirmRequest(BaseModel):
    brief: dict = Field(default_factory=dict)
    identity_action: str = "link"  # link | create | keep_unidentified


class RemindLaterRequest(BaseModel):
    hours: int | None = None


class CallSessionSummary(BaseModel):
    id: int
    dc_user_id: int
    dc_user_name: str
    direction: str
    phone_ref: str
    official_id: int | None
    official_name: str | None
    relationship_id: int | None
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    recording_status: str
    identity_status: str
    processing_status: str
    reminder_at: datetime | None

    @staticmethod
    def of(call: CallSession) -> "CallSessionSummary":
        return CallSessionSummary(
            id=call.id,
            dc_user_id=call.dc_user_id,
            dc_user_name=call.dc_user.name,
            direction=call.direction.value,
            phone_ref=call.phone_ref,
            official_id=call.official_id,
            official_name=call.official.name if call.official else None,
            relationship_id=call.relationship_id,
            started_at=call.started_at,
            ended_at=call.ended_at,
            duration_seconds=call.duration_seconds,
            recording_status=call.recording_status.value,
            identity_status=call.identity_status.value,
            processing_status=call.processing_status.value,
            reminder_at=call.reminder_at,
        )


class CallSessionDetail(CallSessionSummary):
    transcript_text: str | None
    transcript_source: str | None
    brief: dict | None
    recording_status_detail: str | None

    @staticmethod
    def of(call: CallSession) -> "CallSessionDetail":
        base = CallSessionSummary.of(call).model_dump()
        return CallSessionDetail(
            **base,
            transcript_text=call.transcript.text if call.transcript else None,
            transcript_source=call.transcript.source_type if call.transcript else None,
            brief=call.analysis.analysis_json if call.analysis else None,
            recording_status_detail=call.recording.status if call.recording else None,
        )


class CallSessionListResponse(BaseModel):
    items: list[CallSessionSummary]
    total: int


class DcOption(BaseModel):
    id: int
    name: str
