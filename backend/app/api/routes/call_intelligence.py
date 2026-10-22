"""Mobile Call Intelligence: outgoing Click-to-Call, the Knowlarity webhook,
and the DC's pending/history/review workflow. A DC only ever sees/acts on
their own call_session rows (dc_user_id == actor.id) - enforced in every
query here, not just via role, per AC-SEC-002.
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.call_intelligence import CallSession
from ...models.official import Official
from ...models.relationship import Relationship
from ...models.user import Role, User
from ...schemas.call_intelligence import (
    CallerLookupRequest,
    CallerLookupResponse,
    CallerLookupResult,
    CallSessionDetail,
    CallSessionListResponse,
    CallSessionSummary,
    ConfirmRequest,
    CreateOfficialRequest,
    DcOption,
    IncomingNativeCallRequest,
    LinkOfficialRequest,
    ManualTextRequest,
    NativeCallCompleteRequest,
    OutgoingCallRequest,
    RemindLaterRequest,
)
from ...security.deps import get_current_user, require_roles
from ...services import call_intelligence as call_svc
from ...services import knowlarity

settings = get_settings()
router = APIRouter(tags=["call-intelligence"])

_EDITORS = require_roles(Role.DC, Role.RELATIONSHIP_MANAGER, Role.ADMIN)


def _scope_filters(actor: User) -> list:
    """DC: own calls only. RM: their own calls (e.g. CSP calls they place) PLUS calls tied to a
    relationship they own. Admin: all."""
    if actor.role is Role.DC:
        return [CallSession.dc_user_id == actor.id]
    if actor.role is Role.RELATIONSHIP_MANAGER:
        owned = select(Relationship.id).where(Relationship.owner_id == actor.id)
        return [or_(CallSession.dc_user_id == actor.id, CallSession.relationship_id.in_(owned))]
    return []


def _load_scoped(db: Session, call_id: int, actor: User) -> CallSession:
    call = db.get(CallSession, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call session not found")
    if actor.role is Role.DC and call.dc_user_id != actor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call session not found")
    if actor.role is Role.RELATIONSHIP_MANAGER and call.dc_user_id != actor.id:
        # Not the RM's own call - allow only if it is on a relationship they own.
        rel = db.get(Relationship, call.relationship_id) if call.relationship_id else None
        if rel is None or rel.owner_id != actor.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Call session not found")
    return call


@router.post("/calls/outgoing", response_model=CallSessionSummary, status_code=status.HTTP_201_CREATED)
def start_outgoing_call(
    payload: OutgoingCallRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    if not settings.enable_call_intelligence:
        raise HTTPException(status.HTTP_409_CONFLICT, "Call Intelligence is disabled")
    if payload.official_id is not None:
        official = db.get(Official, payload.official_id)
        if official is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Official not found")
        call = call_svc.initiate_outgoing_call(db, dc=actor, official=official)
    else:
        call = call_svc.initiate_manual_call(db, dc=actor, phone=payload.phone)
    db.commit()
    db.refresh(call)
    return CallSessionSummary.of(call)


@router.post("/webhooks/knowlarity/call-completed", status_code=status.HTTP_204_NO_CONTENT)
async def knowlarity_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-knowlarity-signature")
    if not knowlarity.verify_webhook(provided_signature=signature, raw_body=raw_body):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    payload = await request.json()
    call_svc.ingest_webhook(db, payload)
    db.commit()


@router.get("/calls/dc-options", response_model=list[DcOption])
def list_dc_options(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """DCs the caller may filter the call list by. DC: just themselves.
    RM: DCs who have placed/received a call tied to a relationship they own.
    Admin: every DC user."""
    if actor.role is Role.DC:
        return [DcOption(id=actor.id, name=actor.name, role=actor.role.value)]
    if actor.role is Role.RELATIONSHIP_MANAGER:
        # An RM filters by themselves (their own CSP calls) plus any DC on their relationships.
        owned = select(Relationship.id).where(Relationship.owner_id == actor.id)
        rows = db.scalars(
            select(User)
            .join(CallSession, CallSession.dc_user_id == User.id)
            .where(CallSession.relationship_id.in_(owned))
            .distinct()
            .order_by(User.name)
        ).all()
        opts = [DcOption(id=actor.id, name=actor.name, role=actor.role.value)]
        opts += [DcOption(id=u.id, name=u.name, role=u.role.value) for u in rows if u.id != actor.id]
        return opts
    # Admin: every DC and every RM, so CSP calls (RM-owned) can be filtered too.
    rows = db.scalars(
        select(User)
        .where(User.role.in_([Role.DC, Role.RELATIONSHIP_MANAGER]))
        .order_by(User.role, User.name)
    ).all()
    return [DcOption(id=u.id, name=u.name, role=u.role.value) for u in rows]


def _csp_phone_refs(db: Session) -> list[str]:
    """Normalised (last-10-digit) phone numbers of every active CSP - used to filter the call
    list down to calls made to a CSP. Matches how CallSession.phone_ref is stored."""
    from ...models.csp import Csp, CspStatus
    from ...services import phone as phone_svc

    refs: set[str] = set()
    rows = db.execute(
        select(Csp.mobile, Csp.alternate_mobile).where(Csp.status == CspStatus.ACTIVE)
    ).all()
    for mobile, alt in rows:
        for n in (mobile, alt):
            norm = phone_svc.normalize(n)
            if norm:
                refs.add(norm)
    return list(refs)


@router.get("/calls/pending", response_model=CallSessionListResponse)
def list_pending(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    dc_user_id: int | None = Query(default=None),
    csp_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    filters = _scope_filters(actor)
    filters.append(CallSession.processing_status.in_(["review_required", "initiated"]))
    if dc_user_id is not None:
        filters.append(CallSession.dc_user_id == dc_user_id)
    if csp_only:
        filters.append(CallSession.phone_ref.in_(_csp_phone_refs(db)))
    total = db.scalar(select(func.count()).select_from(CallSession).where(*filters)) or 0
    rows = db.scalars(
        select(CallSession).where(*filters).order_by(CallSession.started_at.desc()).limit(limit).offset(offset)
    ).all()
    return CallSessionListResponse(items=[CallSessionSummary.of(c) for c in rows], total=total)


@router.get("/calls/history", response_model=CallSessionListResponse)
def list_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    dc_user_id: int | None = Query(default=None),
    csp_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    filters = _scope_filters(actor)
    if dc_user_id is not None:
        filters.append(CallSession.dc_user_id == dc_user_id)
    if csp_only:
        filters.append(CallSession.phone_ref.in_(_csp_phone_refs(db)))
    total = db.scalar(select(func.count()).select_from(CallSession).where(*filters)) or 0
    rows = db.scalars(
        select(CallSession).where(*filters).order_by(CallSession.started_at.desc()).limit(limit).offset(offset)
    ).all()
    return CallSessionListResponse(items=[CallSessionSummary.of(c) for c in rows], total=total)


@router.post("/calls/lookup", response_model=CallerLookupResponse)
def lookup_caller(
    payload: CallerLookupRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    # An RM records calls with a CSP number (primary or alternate), incoming or outgoing - and
    # nothing else. The app is told to record only when this specific number is a CSP's.
    record_all = actor.role == Role.RELATIONSHIP_MANAGER and call_svc.is_csp_number(db, payload.phone)
    official = call_svc.lookup_caller(db, phone=payload.phone, dc=actor)
    if official is None:
        return CallerLookupResponse(official=None, record_all=record_all)
    return CallerLookupResponse(
        official=CallerLookupResult(
            official_id=official.id,
            name=official.name,
            designation=official.designation,
            organization_unit_name=official.organization_unit_name,
        ),
        record_all=record_all,
    )


@router.post("/calls/native/incoming", response_model=CallSessionDetail, status_code=status.HTTP_201_CREATED)
def incoming_native_call(
    payload: IncomingNativeCallRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    if not settings.enable_call_intelligence:
        raise HTTPException(status.HTTP_409_CONFLICT, "Call Intelligence is disabled")
    call = call_svc.log_incoming_native_call(
        db,
        dc=actor,
        phone=payload.phone,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_seconds=payload.duration_seconds,
        actor=actor,
        direction=payload.direction,
        manual=payload.manual,
    )
    db.commit()
    db.refresh(call)
    return CallSessionDetail.of(call)


@router.get("/calls/{call_id}", response_model=CallSessionDetail)
def get_call(call_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return CallSessionDetail.of(_load_scoped(db, call_id, actor))


_MAX_VOICE_NOTE_BYTES = 20 * 1024 * 1024


@router.post("/calls/{call_id}/voice-note", response_model=CallSessionDetail)
async def voice_note(
    call_id: int,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    kind: str = Form(call_svc.AUDIO_KIND_VOICE_NOTE),
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    """kind=voice_note (default): the DC's own recap. kind=call_recording: the
    call's own audio, accepted only for a CRM official's number (403 otherwise,
    and nothing is stored)."""
    if kind not in (call_svc.AUDIO_KIND_VOICE_NOTE, call_svc.AUDIO_KIND_CALL_RECORDING):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown audio kind")
    call = _load_scoped(db, call_id, actor)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Empty file")
    if len(data) > _MAX_VOICE_NOTE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Voice note too large")
    try:
        call_svc.submit_voice_note(
            db, call, audio_bytes=data, filename=file.filename or "voice-note.m4a", actor=actor, kind=kind
        )
    except call_svc.CallRecordingNotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    db.commit()
    db.refresh(call)
    # Transcribe + brief AFTER the response is sent, so the upload is instant.
    background.add_task(call_svc.transcribe_call_in_background, call.id, "voice_note")
    return CallSessionDetail.of(call)


_VOICE_NOTE_CONTENT_TYPES = {
    ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".mp4": "audio/mp4",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".webm": "audio/webm",
}


@router.get("/calls/{call_id}/voice-note/audio")
def voice_note_audio(call_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    call = _load_scoped(db, call_id, actor)
    if call.voice_note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No voice note for this call")
    path = Path(call.voice_note.secure_object_ref)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice note file is missing")
    content_type = _VOICE_NOTE_CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=content_type, filename=path.name)


@router.delete("/calls/{call_id}/voice-note", response_model=CallSessionDetail)
def delete_voice_note(call_id: int, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)):
    call = _load_scoped(db, call_id, actor)
    try:
        call_svc.discard_voice_note(db, call, actor=actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(call)
    return CallSessionDetail.of(call)


@router.post("/calls/{call_id}/manual-text", response_model=CallSessionDetail)
def manual_text(
    call_id: int, payload: ManualTextRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    call = _load_scoped(db, call_id, actor)
    call_svc.set_manual_text(db, call, payload.text, actor)
    db.commit()
    db.refresh(call)
    return CallSessionDetail.of(call)


@router.post("/calls/{call_id}/identity/link", response_model=CallSessionSummary)
def link_identity(
    call_id: int, payload: LinkOfficialRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    call = _load_scoped(db, call_id, actor)
    try:
        call_svc.link_existing_official(
            db, call, payload.official_id, update_phone=payload.update_phone, actor=actor
        )
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    db.refresh(call)
    return CallSessionSummary.of(call)


@router.post("/calls/{call_id}/identity/create", response_model=CallSessionSummary)
def create_identity(
    call_id: int, payload: CreateOfficialRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    call = _load_scoped(db, call_id, actor)
    try:
        call_svc.create_new_official(db, call, payload.model_dump(), actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    db.refresh(call)
    return CallSessionSummary.of(call)


@router.post("/calls/{call_id}/identity/dismiss", response_model=CallSessionSummary)
def dismiss_identity(call_id: int, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)):
    call = _load_scoped(db, call_id, actor)
    call_svc.keep_unidentified(db, call, actor)
    db.commit()
    db.refresh(call)
    return CallSessionSummary.of(call)


@router.post("/calls/{call_id}/confirm", response_model=CallSessionDetail)
def confirm(
    call_id: int, payload: ConfirmRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    call = _load_scoped(db, call_id, actor)
    try:
        call_svc.confirm_and_log(db, call, actor, payload.brief, payload.identity_action)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    db.refresh(call)
    return CallSessionDetail.of(call)


@router.post("/calls/{call_id}/remind-later", response_model=CallSessionSummary)
def remind_later(
    call_id: int, payload: RemindLaterRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    call = _load_scoped(db, call_id, actor)
    call_svc.remind_later(db, call, payload.hours)
    db.commit()
    db.refresh(call)
    return CallSessionSummary.of(call)


@router.post("/calls/{call_id}/native/complete", response_model=CallSessionDetail)
def complete_native_call(
    call_id: int, payload: NativeCallCompleteRequest, db: Session = Depends(get_db), actor: User = Depends(_EDITORS)
):
    call = _load_scoped(db, call_id, actor)
    call_svc.complete_native_call(
        db,
        call,
        actor=actor,
        ended_at=payload.ended_at,
        duration_seconds=payload.duration_seconds,
        connected=payload.connected,
        recording_engine=payload.recording_engine,
        recording_capability_status=payload.recording_capability_status,
    )
    db.commit()
    db.refresh(call)
    return CallSessionDetail.of(call)
