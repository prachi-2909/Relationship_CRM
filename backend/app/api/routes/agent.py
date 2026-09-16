"""The autonomous agent: trigger a run, review its recommendations, approve or
reject them. Observe + recommend only - a run never writes a real domain
object itself; see services/agent.py for exactly what approving each
recommendation type does.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.agent import (
    AgentRecommendation,
    AgentRun,
    AgentRunScope,
    AgentRunStatus,
    AgentTrigger,
    RecommendationStatus,
    RecommendationType,
    RiskTier,
)
from ...models.relationship import Relationship
from ...models.user import Role, User
from ...schemas.agent import (
    AgentRunDetail,
    AgentRunListResponse,
    AgentRunSummary,
    RecommendationDetail,
    RecommendationListResponse,
    RecommendationSummary,
    RejectRequest,
    RunTriggerRequest,
)
from ...security.deps import get_current_user, require_roles
from ...services import agent as agent_svc

settings = get_settings()
router = APIRouter(prefix="/agent", tags=["agent"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)


def _load_run(db: Session, run_id: int) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent run not found")
    return run


def _load_recommendation(db: Session, rec_id: int) -> AgentRecommendation:
    rec = db.get(AgentRecommendation, rec_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    return rec


@router.post("/runs", response_model=AgentRunDetail, status_code=status.HTTP_201_CREATED)
def trigger_run(
    payload: RunTriggerRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    if not settings.enable_agent:
        raise HTTPException(status.HTTP_409_CONFLICT, "The autonomous agent is disabled")

    if payload.scope is AgentRunScope.RELATIONSHIP:
        if payload.relationship_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "relationship_id is required")
        rel = db.get(Relationship, payload.relationship_id)
        if rel is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Relationship not found")
        is_owner = rel.owner_id == actor.id
        if not (actor.role is Role.ADMIN or is_owner):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only the owner or an admin can run the agent on this relationship"
            )
        run = agent_svc.run_for_relationship(db, rel, actor=actor, trigger=AgentTrigger.MANUAL)
    else:
        run = agent_svc.run_for_portfolio(db, actor, trigger=AgentTrigger.MANUAL)

    db.commit()
    db.refresh(run)
    return AgentRunDetail.of(run)


@router.get("/runs", response_model=AgentRunListResponse)
def list_runs(
    scope: AgentRunScope | None = None,
    trigger: AgentTrigger | None = None,
    status_filter: AgentRunStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    filters = []
    if scope is not None:
        filters.append(AgentRun.scope == scope)
    if trigger is not None:
        filters.append(AgentRun.trigger == trigger)
    if status_filter is not None:
        filters.append(AgentRun.status == status_filter)

    total = db.scalar(select(func.count()).select_from(AgentRun).where(*filters)) or 0
    rows = db.scalars(
        select(AgentRun).where(*filters).order_by(AgentRun.started_at.desc()).limit(limit).offset(offset)
    ).all()
    return AgentRunListResponse(
        items=[AgentRunSummary.of(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
def get_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return AgentRunDetail.of(_load_run(db, run_id))


@router.get("/recommendations", response_model=RecommendationListResponse)
def list_recommendations(
    status_filter: RecommendationStatus | None = Query(default=None, alias="status"),
    type_filter: RecommendationType | None = Query(default=None, alias="type"),
    risk_tier: RiskTier | None = None,
    relationship_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    filters = []
    if status_filter is not None:
        filters.append(AgentRecommendation.status == status_filter)
    if type_filter is not None:
        filters.append(AgentRecommendation.type == type_filter)
    if risk_tier is not None:
        filters.append(AgentRecommendation.risk_tier == risk_tier)
    if relationship_id is not None:
        filters.append(AgentRecommendation.relationship_id == relationship_id)

    total = db.scalar(select(func.count()).select_from(AgentRecommendation).where(*filters)) or 0
    rows = db.scalars(
        select(AgentRecommendation)
        .where(*filters)
        .order_by(AgentRecommendation.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return RecommendationListResponse(
        items=[RecommendationSummary.of(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/recommendations/{rec_id}", response_model=RecommendationDetail)
def get_recommendation(rec_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return RecommendationDetail.of(_load_recommendation(db, rec_id))


@router.post("/recommendations/{rec_id}/approve", response_model=RecommendationDetail)
def approve_recommendation(
    rec_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rec = _load_recommendation(db, rec_id)
    if rec.status is not RecommendationStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Recommendation already decided")
    agent_svc.approve(db, rec, actor)
    db.commit()
    db.refresh(rec)
    return RecommendationDetail.of(rec)


@router.post("/recommendations/{rec_id}/reject", response_model=RecommendationDetail)
def reject_recommendation(
    rec_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rec = _load_recommendation(db, rec_id)
    if rec.status is not RecommendationStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Recommendation already decided")
    agent_svc.reject(db, rec, actor, payload.reason)
    db.commit()
    db.refresh(rec)
    return RecommendationDetail.of(rec)
