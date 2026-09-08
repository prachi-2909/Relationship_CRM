"""Relationships: CRUD, ownership, and the health score."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.official import Official
from ...models.relationship import (
    Importance,
    Relationship,
    RelationshipScoreHistory,
    RelationshipStatus,
    RiskLevel,
)
from ...models.user import Role, User
from ...schemas.relationship import (
    OfficialRef,
    RelationshipCreate,
    RelationshipDetail,
    RelationshipListResponse,
    RelationshipSummary,
    RelationshipUpdate,
    ScoreHistoryEntry,
)
from ...security.deps import get_current_user, require_roles
from ...services import audit
from ...services import scoring

router = APIRouter(prefix="/relationships", tags=["relationships"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)
_SORTABLE = {
    "score": Relationship.score,
    "-score": Relationship.score.desc(),
    "updated_at": Relationship.updated_at,
    "-updated_at": Relationship.updated_at.desc(),
}
_STRATEGIC_HINTS = ("cgm", "dgm", "gm ", "general manager", "chief general")
_IMPORTANT_HINTS = ("agm", "regional manager", "chief manager", "dgm")


def _default_importance(official: Official) -> Importance:
    level = f" {(official.level or '').lower()} "
    if any(h in level for h in _STRATEGIC_HINTS):
        return Importance.STRATEGIC
    if any(h in level for h in _IMPORTANT_HINTS):
        return Importance.IMPORTANT
    return Importance.ROUTINE


def _latest_components(db: Session, rel: Relationship) -> dict | None:
    row = db.scalar(
        select(RelationshipScoreHistory)
        .where(RelationshipScoreHistory.relationship_id == rel.id)
        .order_by(RelationshipScoreHistory.computed_at.desc())
        .limit(1)
    )
    return row.components if row else None


def _detail(db: Session, rel: Relationship) -> RelationshipDetail:
    base = RelationshipSummary.of(rel).model_dump()
    return RelationshipDetail(
        **base,
        official=OfficialRef.model_validate(rel.official),
        score_components=_latest_components(db, rel),
    )


def _load(db: Session, relationship_id: int) -> Relationship:
    rel = db.get(Relationship, relationship_id)
    if rel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relationship not found")
    return rel


@router.get("", response_model=RelationshipListResponse)
def list_relationships(
    mine: bool = False,
    owner_id: int | None = None,
    status_filter: RelationshipStatus | None = Query(default=None, alias="status"),
    importance: Importance | None = None,
    risk_level: RiskLevel | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    q: str | None = None,
    sort: str = "-score",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if sort not in _SORTABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown sort key")

    filters = []
    if mine:
        filters.append(Relationship.owner_id == user.id)
    elif owner_id is not None:
        filters.append(Relationship.owner_id == owner_id)
    if status_filter is not None:
        filters.append(Relationship.status == status_filter)
    if importance is not None:
        filters.append(Relationship.importance == importance)
    if risk_level is not None:
        filters.append(Relationship.risk_level == risk_level)
    if min_score is not None:
        filters.append(Relationship.score >= min_score)
    if q:
        filters.append(
            Relationship.official_id.in_(
                select(Official.id).where(Official.name.ilike(f"%{q}%"))
            )
        )

    total = db.scalar(
        select(func.count()).select_from(Relationship).where(*filters)
    ) or 0
    rows = db.scalars(
        select(Relationship)
        .where(*filters)
        .order_by(_SORTABLE[sort])
        .limit(limit)
        .offset(offset)
    ).all()
    return RelationshipListResponse(
        items=[RelationshipSummary.of(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=RelationshipDetail, status_code=status.HTTP_201_CREATED)
def create_relationship(
    payload: RelationshipCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    official = db.get(Official, payload.official_id)
    if official is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Official not found")
    if db.scalar(
        select(Relationship).where(Relationship.official_id == payload.official_id)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This official already has a relationship"
        )

    owner_id = payload.owner_id
    if owner_id is None and actor.role is Role.RELATIONSHIP_MANAGER:
        owner_id = actor.id  # a manager creating one claims it
    if owner_id is not None and db.get(User, owner_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Owner not found")

    rel = Relationship(
        official_id=payload.official_id,
        owner_id=owner_id,
        importance=payload.importance or _default_importance(official),
        status=RelationshipStatus.NEW,
    )
    db.add(rel)
    db.flush()
    scoring.recompute_and_store(db, rel, reason="created")
    audit.record(
        db,
        action="relationship.create",
        entity_type="relationship",
        entity_id=rel.id,
        actor_id=actor.id,
        after={"official_id": rel.official_id, "owner_id": owner_id},
    )
    db.commit()
    db.refresh(rel)
    return _detail(db, rel)


@router.get("/{relationship_id}", response_model=RelationshipDetail)
def get_relationship(
    relationship_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _detail(db, _load(db, relationship_id))


@router.patch("/{relationship_id}", response_model=RelationshipDetail)
def update_relationship(
    relationship_id: int,
    payload: RelationshipUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rel = _load(db, relationship_id)
    data = payload.model_dump(exclude_unset=True)

    is_owner = rel.owner_id == actor.id
    if not (actor.role is Role.ADMIN or is_owner):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the owner or an admin can change this"
        )
    if "owner_id" in data and actor.role is not Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can reassign")
    if data.get("owner_id") is not None and db.get(User, data["owner_id"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Owner not found")

    before = {
        "status": rel.status.value,
        "importance": rel.importance.value,
        "owner_id": rel.owner_id,
    }
    for key in ("status", "importance", "owner_id", "next_action_at"):
        if key in data:
            setattr(rel, key, data[key])

    audit.record(
        db,
        action="relationship.update",
        entity_type="relationship",
        entity_id=rel.id,
        actor_id=actor.id,
        before=before,
        after={
            "status": rel.status.value,
            "importance": rel.importance.value,
            "owner_id": rel.owner_id,
        },
    )
    db.commit()
    db.refresh(rel)
    return _detail(db, rel)


@router.post("/{relationship_id}/claim", response_model=RelationshipDetail)
def claim_relationship(
    relationship_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rel = _load(db, relationship_id)
    if rel.owner_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already owned")
    rel.owner_id = actor.id
    audit.record(
        db,
        action="relationship.claim",
        entity_type="relationship",
        entity_id=rel.id,
        actor_id=actor.id,
        after={"owner_id": actor.id},
    )
    db.commit()
    db.refresh(rel)
    return _detail(db, rel)


@router.get(
    "/{relationship_id}/score-history", response_model=list[ScoreHistoryEntry]
)
def score_history(
    relationship_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _load(db, relationship_id)
    rows = db.scalars(
        select(RelationshipScoreHistory)
        .where(RelationshipScoreHistory.relationship_id == relationship_id)
        .order_by(RelationshipScoreHistory.computed_at.desc())
        .limit(limit)
    ).all()
    return [ScoreHistoryEntry.model_validate(r) for r in rows]


@router.post("/{relationship_id}/recompute", response_model=RelationshipDetail)
def recompute(
    relationship_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rel = _load(db, relationship_id)
    scoring.recompute_and_store(db, rel, reason="manual recompute")
    audit.record(
        db,
        action="relationship.recompute",
        entity_type="relationship",
        entity_id=rel.id,
        actor_id=actor.id,
        after={"score": rel.score},
    )
    db.commit()
    db.refresh(rel)
    return _detail(db, rel)
