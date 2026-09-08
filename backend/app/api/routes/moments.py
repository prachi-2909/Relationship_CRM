"""Engagement moments: review feed, drafting, approval, and manual send record.

There is no send endpoint. A moment never advances past DRAFT_READY on its own;
APPROVED / SENT_MANUALLY / DISMISSED are all explicit human actions.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.engagement_moment import EngagementMoment, MomentStatus, MomentType
from ...models.relationship import Relationship
from ...models.task import Task, TaskStatus
from ...models.user import Role, User
from ...schemas.engagement_moment import (
    DismissRequest,
    DraftUpdate,
    MomentDetail,
    MomentListResponse,
    MomentSummary,
    SentRequest,
)
from ...security.deps import get_current_user, require_roles
from ...services import audit, moments

settings = get_settings()
router = APIRouter(prefix="/moments", tags=["moments"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)


def _load(db: Session, moment_id: int) -> EngagementMoment:
    moment = db.get(EngagementMoment, moment_id)
    if moment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Moment not found")
    return moment


def _sender_name(db: Session, moment: EngagementMoment) -> str | None:
    rel = db.get(Relationship, moment.relationship_id)
    if rel and rel.owner_id:
        owner = db.get(User, rel.owner_id)
        if owner:
            return owner.name
    return None


@router.get("", response_model=MomentListResponse)
def list_moments(
    status_filter: MomentStatus | None = Query(default=None, alias="status"),
    type_filter: MomentType | None = Query(default=None, alias="type"),
    relationship_id: int | None = None,
    suppressed: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    filters = []
    if status_filter is not None:
        filters.append(EngagementMoment.status == status_filter)
    if type_filter is not None:
        filters.append(EngagementMoment.type == type_filter)
    if relationship_id is not None:
        filters.append(EngagementMoment.relationship_id == relationship_id)
    if suppressed is True:
        filters.append(EngagementMoment.suppressed_reason.is_not(None))
    elif suppressed is False:
        filters.append(EngagementMoment.suppressed_reason.is_(None))

    total = db.scalar(
        select(func.count()).select_from(EngagementMoment).where(*filters)
    ) or 0
    rows = db.scalars(
        select(EngagementMoment)
        .where(*filters)
        .order_by(EngagementMoment.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return MomentListResponse(
        items=[MomentSummary.of(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{moment_id}", response_model=MomentDetail)
def get_moment(
    moment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return MomentDetail.of(_load(db, moment_id))


@router.post("/detect")
def run_detection(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    if not settings.enable_moments:
        raise HTTPException(status.HTTP_409_CONFLICT, "Moment detection is disabled")
    created = moments.detect_all(db)
    db.commit()
    return {"created": created}


@router.post("/{moment_id}/draft", response_model=MomentDetail)
def draft_moment(
    moment_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    if not settings.enable_moments:
        raise HTTPException(status.HTTP_409_CONFLICT, "Moment drafting is disabled")
    moment = _load(db, moment_id)
    if moment.status not in (MomentStatus.DETECTED, MomentStatus.DRAFT_READY):
        raise HTTPException(status.HTTP_409_CONFLICT, "Moment already decided")
    if moment.suppressed_reason and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Suppressed ({moment.suppressed_reason}). Pass force=true to draft anyway.",
        )

    moment.draft_text = moments.build_draft(db, moment, _sender_name(db, moment))
    moment.status = MomentStatus.DRAFT_READY
    audit.record(
        db,
        action="moment.drafted",
        entity_type="engagement_moment",
        entity_id=moment.id,
        actor_id=actor.id,
        after={"forced": force},
    )
    db.commit()
    db.refresh(moment)
    return MomentDetail.of(moment)


@router.patch("/{moment_id}", response_model=MomentDetail)
def edit_draft(
    moment_id: int,
    payload: DraftUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    moment = _load(db, moment_id)
    if moment.status not in (MomentStatus.DRAFT_READY, MomentStatus.DETECTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Moment already decided")
    moment.draft_text = payload.draft_text
    if moment.status is MomentStatus.DETECTED:
        moment.status = MomentStatus.DRAFT_READY
    audit.record(
        db,
        action="moment.draft_edited",
        entity_type="engagement_moment",
        entity_id=moment.id,
        actor_id=actor.id,
    )
    db.commit()
    db.refresh(moment)
    return MomentDetail.of(moment)


@router.post("/{moment_id}/approve", response_model=MomentDetail)
def approve_moment(
    moment_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    moment = _load(db, moment_id)
    if moment.status is not MomentStatus.DRAFT_READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Draft one first")

    moment.status = MomentStatus.APPROVED
    moment.decided_by = actor.id
    moment.decided_at = datetime.now(timezone.utc)

    # Inactivity moments become a follow-up task, not something to send.
    if moment.type is MomentType.INACTIVITY:
        db.add(
            Task(
                relationship_id=moment.relationship_id,
                official_id=moment.official_id,
                title=f"Non-sales check-in with {moment.official.name}",
                detail=moment.draft_text,
                status=TaskStatus.OPEN,
                assigned_to=actor.id,
                created_by=actor.id,
            )
        )

    audit.record(
        db,
        action="moment.approved",
        entity_type="engagement_moment",
        entity_id=moment.id,
        actor_id=actor.id,
        after={"type": moment.type.value},
    )
    db.commit()
    db.refresh(moment)
    return MomentDetail.of(moment)


@router.post("/{moment_id}/sent", response_model=MomentDetail)
def mark_sent(
    moment_id: int,
    payload: SentRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    moment = _load(db, moment_id)
    if moment.status is not MomentStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approve the draft first")
    moment.status = MomentStatus.SENT_MANUALLY
    if payload.outcome:
        evidence = dict(moment.evidence)
        evidence["outcome"] = payload.outcome
        moment.evidence = evidence
    audit.record(
        db,
        action="moment.sent_manually",
        entity_type="engagement_moment",
        entity_id=moment.id,
        actor_id=actor.id,
        after={"outcome": payload.outcome},
    )
    db.commit()
    db.refresh(moment)
    return MomentDetail.of(moment)


@router.post("/{moment_id}/dismiss", response_model=MomentDetail)
def dismiss_moment(
    moment_id: int,
    payload: DismissRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    moment = _load(db, moment_id)
    if moment.status in (MomentStatus.SENT_MANUALLY, MomentStatus.DISMISSED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Moment already closed")
    moment.status = MomentStatus.DISMISSED
    moment.decided_by = actor.id
    moment.decided_at = datetime.now(timezone.utc)
    if payload.reason:
        evidence = dict(moment.evidence)
        evidence["dismiss_reason"] = payload.reason
        moment.evidence = evidence
    audit.record(
        db,
        action="moment.dismissed",
        entity_type="engagement_moment",
        entity_id=moment.id,
        actor_id=actor.id,
        after={"reason": payload.reason},
    )
    db.commit()
    db.refresh(moment)
    return MomentDetail.of(moment)
