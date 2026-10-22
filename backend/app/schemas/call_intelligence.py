"""Schemas for the Mobile Call Intelligence module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from ..models.call_intelligence import CallSession


def _as_utc(value: datetime) -> datetime:
    """SQLite hands datetimes back without tzinfo even though every call timestamp is
    stored as UTC, so they serialized as e.g. "2026-10-05T09:13:15" - which clients
    (JS Date, the Android app) read as *local* time, showing it hours off. Tagging them
    UTC makes the JSON carry a "Z" so each client converts to its own timezone."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class OutgoingCallRequest(BaseModel):
    """Exactly one of official_id (call a known official) or phone (manual
    dial, e.g. a number typed in-app that isn't in the directory) is set."""

    official_id: int | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "OutgoingCallRequest":
        if (self.official_id is None) == (self.phone is None):
            raise ValueError("Provide exactly one of official_id or phone")
        return self


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


class NativeCallCompleteRequest(BaseModel):
    ended_at: UtcDatetime
    duration_seconds: int = Field(ge=0)
    connected: bool
    # Which RecordingEngine ran and what it judged its own capability to be - descriptive only.
    recording_engine: str | None = None
    recording_capability_status: str | None = None


class IncomingNativeCallRequest(BaseModel):
    """A call that happened on the DC's own SIM outside the in-app Call button (an official
    calling in, or the DC dialing from the phone's own dialer), reported after the fact -
    either auto-detected by the app or entered by hand ("manual")."""

    phone: str = Field(min_length=1, max_length=32)
    started_at: UtcDatetime
    ended_at: UtcDatetime
    duration_seconds: int = Field(ge=0)
    direction: Literal["inbound", "outbound"] = "inbound"
    # True when the DC typed the details in rather than the phone measuring them, so the
    # duration isn't mislabeled as a device measurement.
    manual: bool = False


class CallerLookupRequest(BaseModel):
    """The number to look up, sent in the request BODY (not the URL) so it never lands in
    server/proxy access logs - DPDP data-minimisation for a personal phone number."""

    phone: str = Field(min_length=1, max_length=32)


class CallerLookupResult(BaseModel):
    official_id: int
    name: str
    designation: str | None
    organization_unit_name: str | None


class CallerLookupResponse(BaseModel):
    """Wrapper so "no match" is a normal JSON object rather than a bare `null` body, which
    the Android client's Retrofit/kotlinx converter can't decode into a non-null type.

    record_all is the server-authoritative recording signal: True for a Relationship Manager,
    who records EVERY call while logged in (not CRM-gated). When True the app records the call
    even though `official` is null (the number is not a CRM official)."""

    official: CallerLookupResult | None = None
    record_all: bool = False


class CallSessionSummary(BaseModel):
    id: int
    dc_user_id: int
    dc_user_name: str
    direction: str
    phone_ref: str
    official_id: int | None
    official_name: str | None
    csp_id: int | None
    csp_name: str | None
    relationship_id: int | None
    started_at: UtcDatetime
    ended_at: UtcDatetime | None
    duration_seconds: int | None
    duration_source: str | None
    recording_engine: str | None
    recording_capability_status: str | None
    channel: str
    recording_status: str
    identity_status: str
    processing_status: str
    reminder_at: UtcDatetime | None

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
            csp_id=call.csp_id,
            csp_name=call.csp.name if call.csp else None,
            relationship_id=call.relationship_id,
            started_at=call.started_at,
            ended_at=call.ended_at,
            duration_seconds=call.duration_seconds,
            duration_source=call.duration_source,
            recording_engine=call.recording_engine,
            recording_capability_status=call.recording_capability_status,
            channel=call.channel,
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
    has_voice_note: bool = False

    @staticmethod
    def of(call: CallSession) -> "CallSessionDetail":
        base = CallSessionSummary.of(call).model_dump()
        return CallSessionDetail(
            **base,
            transcript_text=call.transcript.text if call.transcript else None,
            transcript_source=call.transcript.source_type if call.transcript else None,
            brief=call.analysis.analysis_json if call.analysis else None,
            recording_status_detail=call.recording.status if call.recording else None,
            has_voice_note=call.voice_note is not None,
        )


class CallSessionListResponse(BaseModel):
    items: list[CallSessionSummary]
    total: int


class DcOption(BaseModel):
    id: int
    name: str
    role: str = "dc"  # "dc" or "relationship_manager" - lets the UI group staff by role
