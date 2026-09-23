"""Mobile Call Intelligence: outgoing Click-to-Call, the Knowlarity webhook,
and the DC's pending/history/review workflow. A DC only ever sees/acts on
their own call_session rows (dc_user_id == actor.id) - enforced in every
query here, not just via role, per AC-SEC-002.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.call_intelligence import CallSession
from ...models.official import Official
from ...models.relationship import Relationship
from ...models.user import Role, User
from ...schemas.call_intelligence import (
    CallSessionDetail,
    CallSessionListResponse,
    CallSessionSummary,
    ConfirmRequest,
    CreateOfficialRequest,
    DcOption,
    LinkOfficialRequest,
    ManualTextRequest,
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
    """DC: own calls only. RM: calls tied to a relationship they own. Admin: all."""
    if actor.role is Role.DC:
        return [CallSession.dc_user_id == actor.id]
    if actor.role is Role.RELATIONSHIP_MANAGER:
        owned = select(Relationship.id).where(Relationship.owner_id == actor.id)
        return [CallSession.relationship_id.in_(owned)]
    return []


def _load_scoped(db: Session, call_id: int, actor: User) -> CallSession:
    call = db.get(CallSession, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call session not found")
    if actor.role is Role.DC and call.dc_user_id != actor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call session not found")
    if actor.role is Role.RELATIONSHIP_MANAGER:
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
    official = db.get(Official, payload.official_id)
    if official is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Official not found")
    call = call_svc.initiate_outgoing_call(db, dc=actor, official=official)
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
        return [DcOption(id=actor.id, name=actor.name)]
    if actor.role is Role.RELATIONSHIP_MANAGER:
        owned = select(Relationship.id).where(Relationship.owner_id == actor.id)
        rows = db.scalars(
            select(User)
            .join(CallSession, CallSession.dc_user_id == User.id)
            .where(CallSession.relationship_id.in_(owned))
            .distinct()
            .order_by(User.name)
        ).all()
        return [DcOption(id=u.id, name=u.name) for u in rows]
    rows = db.scalars(select(User).where(User.role == Role.DC).order_by(User.name)).all()
    return [DcOption(id=u.id, name=u.name) for u in rows]


@router.get("/calls/pending", response_model=CallSessionListResponse)
def list_pending(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    dc_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    filters = _scope_filters(actor)
    filters.append(CallSession.processing_status.in_(["review_required", "initiated"]))
    if dc_user_id is not None:
        filters.append(CallSession.dc_user_id == dc_user_id)
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
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    filters = _scope_filters(actor)
    if dc_user_id is not None:
        filters.append(CallSession.dc_user_id == dc_user_id)
    total = db.scalar(select(func.count()).select_from(CallSession).where(*filters)) or 0
    rows = db.scalars(
        select(CallSession).where(*filters).order_by(CallSession.started_at.desc()).limit(limit).offset(offset)
    ).all()
    return CallSessionListResponse(items=[CallSessionSummary.of(c) for c in rows], total=total)


@router.get("/calls/{call_id}", response_model=CallSessionDetail)
def get_call(call_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return CallSessionDetail.of(_load_scoped(db, call_id, actor))


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
