"""Opportunities: detection, pipeline, activities and outcomes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.opportunity import Opportunity, OpportunityStage, OpportunityStatus
from ...models.relationship import Relationship
from ...models.user import Role, User
from ...schemas.opportunities import (
    OpportunityActivityCreate,
    OpportunityActivityOut,
    OpportunityCreate,
    OpportunityDetail,
    OpportunityListResponse,
    OpportunityStageUpdate,
    OpportunitySummary,
    OpportunityUpdate,
)
from ...security.deps import get_current_user, require_roles
from ...services import audit
from ...services import opportunities as opportunities_svc

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)


def _load(db: Session, opportunity_id: int) -> Opportunity:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunity not found")
    return opp


@router.get("", response_model=OpportunityListResponse)
def list_opportunities(
    relationship_id: int | None = None,
    official_id: int | None = None,
    status_filter: OpportunityStatus | None = Query(default=None, alias="status"),
    stage: OpportunityStage | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    filters = []
    if relationship_id is not None:
        filters.append(Opportunity.relationship_id == relationship_id)
    if official_id is not None:
        filters.append(Opportunity.official_id == official_id)
    if status_filter is not None:
        filters.append(Opportunity.status == status_filter)
    if stage is not None:
        filters.append(Opportunity.stage == stage)

    total = db.scalar(select(func.count()).select_from(Opportunity).where(*filters)) or 0
    rows = db.scalars(
        select(Opportunity)
        .where(*filters)
        .order_by(Opportunity.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return OpportunityListResponse(
        items=[OpportunitySummary.of(o) for o in rows], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=OpportunityDetail, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rel = db.get(Relationship, payload.relationship_id)
    if rel is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Relationship not found")

    opp, created = opportunities_svc.upsert(
        db,
        relationship=rel,
        title=payload.title,
        detail=payload.detail,
        source="Manual entry",
        status=OpportunityStatus.CONFIRMED,
        actor_id=actor.id,
    )
    audit.record(
        db,
        action="opportunity.create" if created else "opportunity.confirm",
        entity_type="opportunity",
        entity_id=opp.id,
        actor_id=actor.id,
        after={"relationship_id": rel.id, "title": opp.title, "status": opp.status.value},
    )
    db.commit()
    db.refresh(opp)
    return OpportunityDetail.of(opp)


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
def get_opportunity(
    opportunity_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return OpportunityDetail.of(_load(db, opportunity_id))


@router.patch("/{opportunity_id}", response_model=OpportunityDetail)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    opp = _load(db, opportunity_id)
    data = payload.model_dump(exclude_unset=True)

    before = {"title": opp.title, "status": opp.status.value}
    if "title" in data:
        opp.title = data["title"]
    if "detail" in data:
        opp.detail = data["detail"]
    if data.get("status") is not None and data["status"] is not opp.status:
        opportunities_svc.set_status(db, opp, data["status"], actor_id=actor.id)

    audit.record(
        db,
        action="opportunity.update",
        entity_type="opportunity",
        entity_id=opp.id,
        actor_id=actor.id,
        before=before,
        after={"title": opp.title, "status": opp.status.value},
    )
    db.commit()
    db.refresh(opp)
    return OpportunityDetail.of(opp)


@router.post("/{opportunity_id}/stage", response_model=OpportunityDetail)
def change_stage(
    opportunity_id: int,
    payload: OpportunityStageUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    opp = _load(db, opportunity_id)
    try:
        opportunities_svc.change_stage(
            db, opp, payload.stage, actor_id=actor.id, outcome_note=payload.outcome_note
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    audit.record(
        db,
        action="opportunity.stage_change",
        entity_type="opportunity",
        entity_id=opp.id,
        actor_id=actor.id,
        after={"stage": opp.stage.value, "outcome_note": opp.outcome_note},
    )
    db.commit()
    db.refresh(opp)
    return OpportunityDetail.of(opp)


@router.get("/{opportunity_id}/activities", response_model=list[OpportunityActivityOut])
def list_activities(
    opportunity_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    opp = _load(db, opportunity_id)
    return [OpportunityActivityOut.model_validate(a) for a in opp.activities]


@router.post(
    "/{opportunity_id}/activities",
    response_model=OpportunityActivityOut,
    status_code=status.HTTP_201_CREATED,
)
def add_activity(
    opportunity_id: int,
    payload: OpportunityActivityCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    opp = _load(db, opportunity_id)
    try:
        activity = opportunities_svc.log_activity(
            db,
            opp,
            type_=payload.type,
            note=payload.note,
            occurred_at=payload.occurred_at,
            actor_id=actor.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    audit.record(
        db,
        action="opportunity.activity_log",
        entity_type="opportunity",
        entity_id=opp.id,
        actor_id=actor.id,
        after={"type": activity.type.value},
    )
    db.commit()
    db.refresh(activity)
    return OpportunityActivityOut.model_validate(activity)
