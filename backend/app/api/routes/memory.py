"""Semantic memory: durable facts about an official. Read is open to any
authenticated user (matching the Supervisor's existing lack of ownership
scoping); writes/verification are RM/Admin only."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.official import Official
from ...models.semantic_memory import SemanticMemoryFact
from ...models.user import Role, User
from ...schemas.memory import FactCreate, FactOut, FactRejectRequest, InsightOut
from ...security.deps import get_current_user, require_roles
from ...services import semantic_memory as semantic_memory_svc
from ...services import strategic_insight

router = APIRouter(tags=["memory"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)
_VIEWERS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER, Role.APPROVER_VIEWER)


def _load_official(db: Session, official_id: int) -> Official:
    official = db.get(Official, official_id)
    if official is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")
    return official


def _load_fact(db: Session, official_id: int, fact_id: int) -> SemanticMemoryFact:
    fact = db.get(SemanticMemoryFact, fact_id)
    if fact is None or fact.official_id != official_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fact not found")
    return fact


@router.get("/officials/{official_id}/facts", response_model=list[FactOut])
def list_facts(
    official_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_VIEWERS),
):
    _load_official(db, official_id)
    return [FactOut.of(f) for f in semantic_memory_svc.facts_for_official(db, official_id, limit=100)]


@router.post("/officials/{official_id}/facts", response_model=FactOut, status_code=status.HTTP_201_CREATED)
def create_fact(
    official_id: int,
    payload: FactCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    _load_official(db, official_id)
    fact = semantic_memory_svc.upsert_fact(
        db,
        official_id=official_id,
        relationship_id=payload.relationship_id,
        fact_text=payload.fact_text,
        fact_key=payload.fact_key,
        confidence=100,
        source_type="human_edit",
        created_by=actor.id,
    )
    if fact is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That field is already tracked elsewhere")
    db.commit()
    db.refresh(fact)
    return FactOut.of(fact)


@router.post("/officials/{official_id}/facts/{fact_id}/verify", response_model=FactOut)
def verify_fact(
    official_id: int,
    fact_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    fact = _load_fact(db, official_id, fact_id)
    semantic_memory_svc.verify_fact(db, fact, actor)
    db.commit()
    db.refresh(fact)
    return FactOut.of(fact)


@router.post("/officials/{official_id}/facts/{fact_id}/reject", response_model=FactOut)
def reject_fact(
    official_id: int,
    fact_id: int,
    payload: FactRejectRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    fact = _load_fact(db, official_id, fact_id)
    semantic_memory_svc.reject_fact(db, fact, actor, payload.reason)
    db.commit()
    db.refresh(fact)
    return FactOut.of(fact)


@router.get("/officials/{official_id}/insights", response_model=list[InsightOut])
def list_insights(
    official_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_VIEWERS),
):
    _load_official(db, official_id)
    return [InsightOut.of(i) for i in strategic_insight.latest_for_official(db, official_id, limit=20)]


@router.post("/officials/{official_id}/insights/recompute")
def recompute_insights(
    official_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_EDITORS),
):
    _load_official(db, official_id)
    created = strategic_insight.recompute_for_official(db, official_id)
    db.commit()
    return {"created": created}
